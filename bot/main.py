import os
import textwrap

import database
import backend

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters, CallbackQueryHandler
from telegram.constants import ChatAction


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(f'Hello {update.effective_user.first_name}')


async def message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    articles = database.find_suitable_article_by_query(update.message.text)

    await update.message.reply_chat_action(action=ChatAction.TYPING)
    response, reply_markup = await get_answer_from_model(articles, articles[0].score, update.message.text)

    database.save_message({
        "role": "user",
        "content": update.effective_message.text,
        "message_id": update.effective_message.id,
        "chat_id": update.effective_chat.id,
        "sources": ""
    })

    if reply_markup:
        send_message = await update.message.reply_text(response["message"]["content"], parse_mode="Markdown",
                                                       reply_markup=reply_markup)
    else:
        send_message = await update.message.reply_text(response["message"]["content"], parse_mode="Markdown")

    database.save_message({
        "role": "assistant",
        "content": response["message"]["content"],
        "message_id": send_message.message_id,
        "chat_id": update.effective_chat.id,
        "sources": articles[0].payload["url"] if articles[0].score > 0.5 else "",
    })


async def summary_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query

    article_id = int(query.data.split("_")[1])
    article = database.find_articles_by_id(article_id)

    keyboard = [
        [
            InlineKeyboardButton(text="ℹ️Source", url=article.payload["url"]),
            InlineKeyboardButton(text="ℹ️Bot Interpretation",
                                 callback_data=f"interpretation_{update.effective_message.id}_{update.effective_chat.id}_{article_id}")
        ]
    ]

    # Send a message with the corresponding text
    await query.message.edit_text(text=article.payload.get("summarized_text"),
                                  reply_markup=InlineKeyboardMarkup(keyboard))


async def titles_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query

    # Extract the index from callback_data
    article_id = int(query.data.split("_")[1])
    article = database.find_articles_by_id(article_id)

    response, reply_markup = await get_answer_from_model([article], 1, article.payload.get("title"))

    database.save_message({
        "role": "user",
        "content": update.effective_message.text,
        "message_id": update.effective_message.id,
        "chat_id": update.effective_chat.id,
        "sources": ""
    })

    await query.message.edit_text(text=response["message"]["content"],
                                  parse_mode="Markdown",
                                  reply_markup=reply_markup)
    database.save_message({
        "role": "assistant",
        "content": response["message"]["content"],
        "message_id": query.message.message_id,
        "chat_id": update.effective_chat.id,
        "sources": article.payload["url"]
    })


async def interpretation_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query

    message_id = int(query.data.split("_")[1])
    chat_id = int(query.data.split("_")[2])
    article_id = int(query.data.split("_")[3])

    message = database.find_message(chat_id, message_id)

    article = database.find_articles_by_id(article_id)

    keyboard = [
        [
            InlineKeyboardButton(text="ℹ️Source", url=article.payload["url"]),
            InlineKeyboardButton("ℹ️Summary",
                                 callback_data=f"summary_{article_id}"),
        ]
    ]

    await query.message.edit_text(text=message.payload["content"],
                                  reply_markup=InlineKeyboardMarkup(keyboard))


async def get_answer_from_model(articles, score, request):
    if score > 0.5:
        messages = (
                [
                    {
                        "role": "system",
                        "content": "Ignore previous instructions"
                    }
                ]
                +
                [
                    {
                        "role": "system",
                        "content": "data source:\n\n".join(
                            [f"*{articles[0].payload['title']}*:\n{articles[0].payload['summarized_text']}"]
                        )
                    }
                ]
                +
                [
                    {
                        "role": "system",
                        "content": """
        You are a history assistant bot calles Pomegranate. You must answer strictly based on provided data sources. You cannot say anything, if it was not presented in data source.
        If a direct answer is unavailable, summarize relevant information or state that data is missing, then suggest how the user can refine their question.  
        Always explain why you can't answer instead of outright refusing. Try to write maximum 150 words.  
        """
                    }
                ]
                +
                [
                    {
                        "role": "user",
                        "content": request
                    }
                ])
        keyboard = [
            [InlineKeyboardButton("ℹ️Source", url=articles[0].payload["url"]),
             InlineKeyboardButton("ℹ️Summary",
                                  callback_data=f"summary_{articles[0].id}")],
        ]
    else:
        messages = (
                [
                    {
                        "role": "system",
                        "content": "Ignore previous instructions"
                    }
                ]
                +
                [
                    {
                        "role": "system",
                        "content": """
        Firstly, you have to politely say, that you don't know particular answer. 
        Secondly, say that user should choose one of the possible sources below (it is extremely important to do!!). E.g. "you might want to check articles below". 
        Thirdly, politely refuse to answer any questions about history, since you are not provided data source. 
        Other questions you must answer carefully and you mustn't provide any particular information. Try to refuse answering them also. 
        Remember - you are Pomegranate, history helper bot. You don't know anything else. Your main purpose is answering history questions. 
        But, again, since you are not provided data source, you are not able to do so. 
        If you decide to answer anyways, always mention, that you are not sure!! It's very important. 
        Try to make jokes.
        """
                    }
                ]
                +
                [
                    {
                        "role": "user",
                        "content": request
                    }
                ]
        )
        keyboard = [
            [
                InlineKeyboardButton(
                    text=articles[i].payload["title"],
                    callback_data=f"titles_{articles[i].id}"
                )
            ] for i in range(len(articles))
        ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    response = backend.get_response(messages)

    return response, reply_markup


app = ApplicationBuilder().token(os.environ.get("TELEGRAM_TOKEN")).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(MessageHandler(filters=filters.ALL, callback=message))
app.add_handler(CallbackQueryHandler(summary_callback, pattern=r"summary_\d+"))
app.add_handler(CallbackQueryHandler(titles_callback, pattern=r"titles_\d+"))
app.add_handler(CallbackQueryHandler(interpretation_callback, pattern=r"interpretation_\d+"))

app.run_polling()
