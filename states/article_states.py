from aiogram.fsm.state import State, StatesGroup

class ArticleWizard(StatesGroup):
    waiting_for_article_text = State()
