# DZ-TENDERS-MVP

> Automated Algerian public tenders scraper with intelligent filtering and Telegram notifications.

## Overview

DZ-TENDERS-MVP is a Python project that:
- Scrapes tenders from multiple government websites (ADE, ONA, AlgeriaTenders).
- Filters tenders based on marketing targets (8 business families).
- Classifies tenders with a weighted scoring system and Arabic NLP support.
- Sends automatic reports to Telegram (text + Excel file).

## Features

- Multi-source crawling (ADE, ONA, AlgeriaTenders)
- Intelligent Arabic filtering (prefix and word-boundary handling)
- Weighted scoring classification
- Support for 8 marketing families
- Telegram notifications with Excel attachment
- Secure secrets storage with `.env` + `.gitignore`

## Tech Stack

![Python](https://img.shields.io/badge/Python-3776AB?style=for-the-badge&logo=python&logoColor=white)
![Pandas](https://img.shields.io/badge/Pandas-150458?style=for-the-badge&logo=pandas&logoColor=white)
![Telegram](https://img.shields.io/badge/Telegram-26A5E4?style=for-the-badge&logo=telegram&logoColor=white)
![Git](https://img.shields.io/badge/Git-F05032?style=for-the-badge&logo=git&logoColor=white)

## Project Structure
