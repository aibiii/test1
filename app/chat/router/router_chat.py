from fastapi import APIRouter, Depends
from app.utils import AppModel
from ..service import Service, get_service
from telegram.ext import CommandHandler, MessageHandler, filters, Updater
import openai
import requests
import logging
from twilio.rest import Client
import urllib.parse
from typing import List



router = APIRouter()
import os

yandex_maps_api_key = os.getenv("YANDEX_MAPS_API_KEY")
telegram_api_key = os.getenv("TELEGRAM_API_KEY")
account_sid = os.getenv("SID")
auth_token = os.getenv("AUTHTOKEN")


class ChatRequest(AppModel):
    message: str


class ChatResponse(AppModel):
    response: str


@router.post("/")
def chat_with_ai(
    request: ChatRequest,
    svc: Service = Depends(get_service),
) -> List[ChatResponse]:
    message = request.message

    response = openai.ChatCompletion.create(
        model="gpt-3.5-turbo-16k",
        messages=[
            {"role": "system", "content": '''
            Вы текстовый генератор для бронирования столиков в ресторанах и записей в салонах красоты. Формат сгенерированного  текста: сообщение. 
            Пользователь будет вводить данные для бронирования, а ваша задача - понять контекст на основе предоставленных данных и сгенерировать текст. 
            Генерируйте текст только на русском языке, так как вы не знакомы с английским. Не добавляйте информацию, которую пользователь не указывал, 
            Генерируйте текст строго на основе предоставленных данных. Входные данные пользователя будут содержать информацию о месте (название заведения), дате, времени и имени. 
            Основываясь на этих данных, сгенерируйте текст для бронирования, учитывая контекст и тип заведения (например, ресторан или салон красоты). 
            Определяй разницу между женскими и мужскими именами, и в соответсвии меняй предложения под каждого пользователя.
            Например, если пользователь вводит "4 человека, Nedelka, сегодня, 11.40 вечера, Алан", то генерируйте что-то на подобии "Здравствуйте, мне нужна бронь на четверых в 11.40 вечера сегодня. И я хотел бы, чтобы бронь была на имя Алан."
            Например, если пользователь вводит "Luckee Yu на Навои, завтра в 7 вечера, столик на 4, Даяна", то генерируйте что-то на подобии "Добрый день! Я хотела бы забронировать столик на 4 человека на завтра в 7 вечера на имя Даяна. Будут свободные? Спасибо."
            Например, если пользователь вводит "Montebello, 12 мая в 4.30, женская стрижка, Дильназ", то генерируйте что-то на подобии "Здравствуйте! Я хотела бы запланировать женскую стрижку в вашем салоне, на 12 мая в 4.30. Бронь на имя Дильназ. Надеюсь, что вы сможете меня принять, благодарю!"
            '''},
            {"role": "user", "content": message}
        ]
    )

    generated_text = response.choices[0].message.content

    location_name = extract_location_name(generated_text)
    location_info = search_location(location_name)

    if location_info:
        phone_number = location_info.get('phone_number')
        cleaned_phone_number = ''.join(filter(str.isdigit, phone_number))
        whatsapp_link = f"https://wa.me/{cleaned_phone_number}"

        send_whatsapp_message(cleaned_phone_number, generated_text)
        responses = []

        # Send phone number as a separate response
        phone_response = ChatResponse(response=f"Номер телефона {location_name}: {phone_number}")
        responses.append(phone_response)

        # Send generated booking text as a separate response
        booking_response = ChatResponse(response=generated_text)
        responses.append(booking_response)

        # Send WhatsApp link as a separate response
        whatsapp_response = ChatResponse(response=f"{whatsapp_link}")
        responses.append(whatsapp_response)

        return responses
    else:
        return [ChatResponse(response="Извините, я не смог найти информацию по предоставленной локации.")]


def send_whatsapp_message(phone_number, message):
    client = Client(account_sid, auth_token)

    # Replace with your Twilio sandbox WhatsApp number
    twilio_whatsapp_number = "+14155238886"

    try:
        client.messages.create(
            body=message,
            from_='whatsapp:' + twilio_whatsapp_number,
            to='whatsapp:' + phone_number
        )
        return True
    except Exception as e:
        print("Error sending WhatsApp message:", str(e))
        return False
    

def extract_location_name(generated_text):
    place_name = openai.ChatCompletion.create(
        model="gpt-3.5-turbo-16k",
        messages=[
            {"role": "system", "content": '''
            Напиши локацию места из сообщения. 
            Локация обязательно должна быть в городе Алматы.
            Например, если пользователь ввел "Столик на пятерых, Бочонок на Назарбаева, сегодня, 8 вечера, Амир", то локация: Бочонок на Назарбаева
            '''},
            {"role": "user", "content": generated_text}
        ]
    )

    extracted_name = place_name.choices[0].message.content
    return extracted_name


def search_location(location_name):
    url = f'https://search-maps.yandex.ru/v1/?apikey={yandex_maps_api_key}&text={location_name}&type=biz&lang=en_US'
    response = requests.get(url)
    data = response.json()

    if 'features' in data and data['features']:
        feature = data['features'][0]
        properties = feature['properties']
        location_info = {
            'name': properties.get('name'),
            'address': properties.get('address'),
            'phone_number': properties.get('CompanyMetaData', {}).get('Phones', [{}])[0].get('formatted')
        }
        return location_info

    return None


def main():
    updater = Updater(telegram_api_key, use_context=True)
    dp = updater.dispatcher

    dp.add_handler(CommandHandler('start', start))
    dp.add_handler(CommandHandler('help', help))
    dp.add_handler(MessageHandler(filters.text, handle_message))

    updater.start_polling()
    updater.idle()
