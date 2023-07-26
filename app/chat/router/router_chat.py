from fastapi import APIRouter, Depends
from app.utils import AppModel
from ..service import Service, get_service
from telegram.ext import CommandHandler, MessageHandler, filters, Updater
import openai
import requests
import logging
from twilio.rest import Client
import urllib.parse


router = APIRouter()
import os

yandex_maps_api_key = os.getenv("YANDEX_MAPS_API_KEY")
telegram_api_key = os.getenv("TELEGRAM_API_KEY")
account_sid = os.getenv("ACCOUNT_SID")
auth_token = os.getenv("AUTH_TOKEN")


class ChatRequest(AppModel):
    message: str


class ChatResponse(AppModel):
    response: str


@router.post("/")
def chat_with_ai(
    request: ChatRequest,
    svc: Service = Depends(get_service),
) -> ChatResponse:
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

    # Extract the location name from the generated text
    location_name = extract_location_name(generated_text)

    # Search for the location using the Yandex Maps API
    location_info = search_location(location_name)

    if location_info:
        # Extract the phone number from the location info
        phone_number = location_info.get('phone_number')
        whatsapp_link = f"https://api.whatsapp.com/send?phone={urllib.parse.quote(phone_number)}"

        # Send the phone number to the user
        # Here, you can use a messaging service or directly send the response to the user
        # For simplicity, let's assume you directly send the response
        response_text = f"Номер телефона {location_name}: {phone_number}\n\n{generated_text}"
        response_with_whatsapp = f"{response_text}\n\nСсылка на WhatsApp: {whatsapp_link}"
        return ChatResponse(response=response_with_whatsapp)
    else:
        return ChatResponse(response=f"Извините, я не смог найти информацию по предоставленной локации.")


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
