# DZ-TENDERS-MVP

Automated Algerian public tenders scraper with intelligent filtering and Telegram notifications.

## Features

- Multi-source crawling (ADE, ONA, AlgeriaTenders)
- Intelligent Arabic filtering
- Weighted scoring classification
- Support for 8 marketing families
- Telegram notifications with Excel attachment
- Secure secrets storage with .env + .gitignore

## Tech Stack

- Python 3.12
- Pandas
- python-dotenv
- Requests
- Telegram Bot API

## Installation

1. Clone the repository:

git clone https://github.com/mamourgroupe-ctrl/dz-tenders-mvp.git
cd dz-tenders-mvp

2. Create virtual environment:

python -m venv venv
.\venv\Scripts\Activate.ps1

3. Install dependencies:

pip install -r requirements.txt

4. Configure environment variables:

Create a .env file with:

TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_CHAT_ID=your_chat_id

5. Run the project:

python test_run.py

## Intelligent Filtering System

The project uses a weighted scoring algorithm:

- Target entity match: 4 points
- Keyword match: 2 points
- Product match: 3 points
- Minimum threshold: 3 points

## Supported Marketing Families

1. Agriculture and Livestock
2. Agricultural and Water Services
3. Construction and Public Works
4. Trade and Distribution
5. Industry, Mining and Energy
6. Tourism, Hospitality and Services
7. Public Facilities
8. Households and Individuals

## Security

- Never commit .env to Git
- Use python-dotenv to load variables
- If a token is exposed, revoke it from @BotFather

## Contact

MAMOUR GROUP
Email: mamourgroupe@gmail.com
GitHub: https://github.com/mamourgroupe-ctrl
