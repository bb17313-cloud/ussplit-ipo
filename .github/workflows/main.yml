name: US Market Movers Bot

on:
  schedule:
    # يعمل تلقائياً كل 5 دقائق من الإثنين إلى السبت (لتغطية جلسة ما بعد الإغلاق فجر السبت بتوقيت السعودية)
    - cron: '*/5 * * * 1-6'
  workflow_dispatch: # يسمح لك بتشغيل البوت يدوياً في أي وقت من تبويب Actions للتجربة

jobs:
  run-bot:
    runs-on: ubuntu-latest

    steps:
      - name: Checkout repository
        uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - name: Run Market Scanner
        env:
          TELEGRAM_TOKEN: ${{ secrets.TELEGRAM_TOKEN }}
          TELEGRAM_CHAT_ID: ${{ secrets.TELEGRAM_CHAT_ID }}
        run: python main.py
