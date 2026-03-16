#!/usr/bin/env python3
"""
Выгрузка N-gramm напрямую из MySQL базы данных butik28feb
Вместо парсинга сайта - выгружает данные из таблиц.

Требует .env файл с параметрами подключения:
DB_HOST=
DB_PORT=
DB_USER=
DB_PASSWORD=
DB_NAME=
"""

import os
import re
import csv
import json
import argparse
from datetime import datetime
from collections import defaultdict
from typing import Dict, Set, List, Tuple
from dotenv import load_dotenv
import mysql.connector
from mysql.connector import Error
import nltk

# =============================================================================
# КОНФИГУРАЦИЯ
# =============================================================================

# Файлы
OUTPUT_JSON = 'ngram_results_mysql.json'
OUTPUT_CSV = 'ngram_results_mysql.csv'
ENV_FILE = '.env'

# N-gramm настройки
MIN_NGRAM = 1  # Униграммы
MAX_NGRAM = 6  # До 6-gram

# =============================================================================
# ГЛОБАЛЬНЫЕ ПЕРЕМЕННЫЕ
# =============================================================================

stop_words: Set[str] = set()
ngram_stats: Dict[str, Dict] = defaultdict(lambda: {"ids": [], "total": 0})

# =============================================================================
# ИНИЦИАЛИЗАЦИЯ
# =============================================================================

def init_stop_words() -> None:
    """Загружает стоп-слова из NLTK."""
    global stop_words

    try:
        nltk.data.find('corpora/stopwords')
    except LookupError:
        print("Скачиваю стоп-слова NLTK...")
        nltk.download('stopwords')

    from nltk.corpus import stopwords
    stop_words = set(stopwords.words('russian'))
    stop_words.update(stopwords.words('english'))

    # Дополнительные стоп-слова
    additional_stopwords = {
        'ваш', 'который', 'свой', 'этот', 'тот', 'такой', 'какой', 'какой-то',
        'каждый', 'любой', 'другой', 'некий', 'весь', 'сам', 'наш', 'их',
        'его', 'её', 'их', 'чего', 'тем', 'том', 'этому', 'этим', 'этом',
        'могу', 'может', 'можно', 'надо', 'нужно', 'следует',
        'сайт', 'страница', 'раздел', 'меню', 'кнопка', 'ссылка',
    }
    stop_words.update(additional_stopwords)

    print(f"✅ Загружено {len(stop_words)} стоп-слов")

def load_custom_stop_words(filename: str = 'stop.csv') -> None:
    """Загружает кастомные стоп-слова из CSV файла."""
    global stop_words

    try:
        import csv
        with open(filename, 'r', encoding='utf-8') as f:
            reader = csv.reader(f)
            for row in reader:
                if row and row[0]:
                    word = row[0].strip().lower()
                    if word:
                        stop_words.add(word)

        print(f"✅ Загружено дополнительных стоп-слов из {filename}")

    except FileNotFoundError:
        print(f"⚠️  Файл {filename} не найден, использую только NLTK")

# =============================================================================
# ПОДКЛЮЧЕНИЕ К MYSQL
# =============================================================================

def connect_to_mysql() -> mysql.connector.MySQLConnection:
    """Подключается к MySQL базе данных."""
    load_dotenv(ENV_FILE)

    config = {
        'host': os.getenv('DB_HOST', 'localhost'),
        'port': int(os.getenv('DB_PORT', 3306)),
        'user': os.getenv('DB_USER'),
        'password': os.getenv('DB_PASSWORD'),
        'database': os.getenv('DB_NAME'),
        'charset': 'utf8mb4',
        'collation': 'utf8mb4_unicode_ci',
    }

    # Проверка обязательных параметров
    if not config['user'] or not config['password']:
        raise ValueError("DB_USER и DB_PASSWORD должны быть указаны в .env файле")

    try:
        connection = mysql.connector.connect(**config)
        if connection.is_connected():
            db_info = connection.server_info
            print(f"✅ Подключено к MySQL Server версии {db_info}")
            return connection

    except Error as e:
        raise Exception(f"Ошибка подключения к MySQL: {e}")

# =============================================================================
# ЗАГРУЗКА ДАННЫХ ИЗ ТАБЛИЦ
# =============================================================================

def fetch_products(connection: mysql.connector.MySQLConnection) -> List[Dict]:
    """Загружает данные из таблицы shop_product."""
    query = """
        SELECT id, name, summary, description
        FROM shop_product
        WHERE status != 0
          AND (description IS NOT NULL OR summary IS NOT NULL OR name IS NOT NULL)
    """

    cursor = connection.cursor(dictionary=True)
    cursor.execute(query)

    results = []
    for row in cursor:
        text_parts = []

        if row.get('name'):
            text_parts.append(row['name'])

        if row.get('summary'):
            text_parts.append(row['summary'])

        if row.get('description'):
            text_parts.append(row['description'])

        if text_parts:
            results.append({
                'id': f"shop_product_{row['id']}",
                'text': ' '.join(text_parts)
            })

    cursor.close()
    print(f"✅ Загружено {len(results)} записей из shop_product")
    return results

def fetch_products_names_only(connection: mysql.connector.MySQLConnection) -> List[Dict]:
    """Загружает ТОЛЬКО name из таблицы shop_product."""
    query = """
        SELECT id, name
        FROM shop_product
        WHERE status != 0 AND name IS NOT NULL
    """

    cursor = connection.cursor(dictionary=True)
    cursor.execute(query)

    results = []
    for row in cursor:
        if row.get('name'):
            results.append({
                'id': f"shop_product_{row['id']}",
                'text': row['name']
            })

    cursor.close()
    print(f"✅ Загружено {len(results)} записей из shop_product (только name)")
    return results

def fetch_blog_posts(connection: mysql.connector.MySQLConnection) -> List[Dict]:
    """Загружает данные из таблицы blog_post."""
    query = """
        SELECT id, url, title, text
        FROM blog_post
        WHERE text IS NOT NULL OR title IS NOT NULL
    """

    cursor = connection.cursor(dictionary=True)
    cursor.execute(query)

    results = []
    for row in cursor:
        text_parts = []

        if row.get('title'):
            text_parts.append(row['title'])

        if row.get('text'):
            text_parts.append(row['text'])

        if text_parts:
            results.append({
                'id': f"blog_post_{row['id']}",
                'text': ' '.join(text_parts)
            })

    cursor.close()
    print(f"✅ Загружено {len(results)} записей из blog_post")
    return results

def fetch_categories(connection: mysql.connector.MySQLConnection) -> List[Dict]:
    """Загружает данные из таблицы shop_category."""
    query = """
        SELECT id, name, description, seo_description
        FROM shop_category
        WHERE status != 0
          AND (description IS NOT NULL OR seo_description IS NOT NULL OR name IS NOT NULL)
    """

    cursor = connection.cursor(dictionary=True)
    cursor.execute(query)

    results = []
    for row in cursor:
        text_parts = []

        if row.get('name'):
            text_parts.append(row['name'])

        if row.get('description'):
            text_parts.append(row['description'])

        if row.get('seo_description'):
            text_parts.append(row['seo_description'])

        if text_parts:
            results.append({
                'id': f"shop_category_{row['id']}",
                'text': ' '.join(text_parts)
            })

    cursor.close()
    print(f"✅ Загружено {len(results)} записей из shop_category")
    return results

def fetch_brands(connection: mysql.connector.MySQLConnection) -> List[Dict]:
    """Загружает данные из таблицы shop_productbrands."""
    query = """
        SELECT id, name, description, seo_description, `h1`
        FROM shop_productbrands
        WHERE hidden != 1
          AND (description IS NOT NULL OR seo_description IS NOT NULL
               OR `h1` IS NOT NULL OR name IS NOT NULL)
    """

    cursor = connection.cursor(dictionary=True)
    cursor.execute(query)

    results = []
    for row in cursor:
        text_parts = []

        if row.get('name'):
            text_parts.append(row['name'])

        if row.get('h1'):
            text_parts.append(row['h1'])

        if row.get('description'):
            text_parts.append(row['description'])

        if row.get('seo_description'):
            text_parts.append(row['seo_description'])

        if text_parts:
            results.append({
                'id': f"shop_productbrands_{row['id']}",
                'text': ' '.join(text_parts)
            })

    cursor.close()
    print(f"✅ Загружено {len(results)} записей из shop_productbrands")
    return results

def fetch_tags(connection: mysql.connector.MySQLConnection) -> List[Dict]:
    """Загружает данные из таблицы shop_tageditor_tag."""
    query = """
        SELECT id, title, description, description_extra
        FROM shop_tageditor_tag
        WHERE description IS NOT NULL OR description_extra IS NOT NULL OR title IS NOT NULL
    """

    cursor = connection.cursor(dictionary=True)
    cursor.execute(query)

    results = []
    for row in cursor:
        text_parts = []

        if row.get('title'):
            text_parts.append(row['title'])

        if row.get('description'):
            text_parts.append(row['description'])

        if row.get('description_extra'):
            text_parts.append(row['description_extra'])

        if text_parts:
            results.append({
                'id': f"shop_tageditor_tag_{row['id']}",
                'text': ' '.join(text_parts)
            })

    cursor.close()
    print(f"✅ Загружено {len(results)} записей из shop_tageditor_tag")
    return results

# =============================================================================
# ОБРАБОТКА ТЕКСТА
# =============================================================================

def normalize_text(text: str) -> str:
    """Нормализует текст: нижний регистр, удаление пунктуации."""
    text = text.lower()
    text = re.sub(r'[^a-zа-яё\s]', ' ', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text

def tokenize(text: str) -> List[str]:
    """Разбивает текст на токены."""
    return text.split()

def generate_ngrams(tokens: List[str]) -> Dict[str, int]:
    """Генерирует n-gramm с частотой и фильтрует стоп-слова."""
    from collections import Counter
    ngrams = []

    for n in range(MIN_NGRAM, MAX_NGRAM + 1):
        for i in range(len(tokens) - n + 1):
            gram = tuple(tokens[i:i + n])

            # Фильтруем: если хотя бы одно слово стоп-слово, пропускаем
            if not any(word in stop_words for word in gram):
                if len(gram) > 0:
                    ngrams.append(' '.join(gram))

    # Считаем частоту каждой n-gramm
    return dict(Counter(ngrams))

# =============================================================================
# ОБРАБОТКА ДАННЫХ
# =============================================================================

def process_records(records: List[Dict]) -> None:
    """Обрабатывает записи и обновляет статистику N-gramm."""
    total_records = len(records)

    for i, record in enumerate(records):
        record_id = record['id']
        text = record['text']

        # Нормализация и токенизация
        normalized = normalize_text(text)
        tokens = tokenize(normalized)

        if len(tokens) < MIN_NGRAM:
            continue

        # Генерация N-gramm с частотой
        ngrams_with_freq = generate_ngrams(tokens)

        # Обновление статистики
        for ngram, frequency in ngrams_with_freq.items():
            ngram_stats[ngram]['total'] += frequency  # Добавляем частоту (все вхождения)
            if record_id not in ngram_stats[ngram]['ids']:
                ngram_stats[ngram]['ids'].append(record_id)  # Уникальные ID

        # Прогресс каждые 1000 записей
        if (i + 1) % 1000 == 0:
            print(f"⏳ Обработано: {i + 1}/{total_records}")

# =============================================================================
# СОХРАНЕНИЕ РЕЗУЛЬТАТОВ
# =============================================================================

def get_output_dir() -> str:
    """Создает и возвращает путь к папке с текущей датой."""
    today = datetime.now().strftime('%Y-%m-%d')
    output_dir = os.path.join(os.getcwd(), f'ngram_results_{today}')

    # Создаем папку если не существует
    os.makedirs(output_dir, exist_ok=True)

    return output_dir

def save_json() -> None:
    """Сохраняет результаты в JSON с ID источников."""
    data = {}

    for ngram, stats in ngram_stats.items():
        data[ngram] = {
            'id': stats['ids'],
            'total': stats['total']
        }

    output_dir = get_output_dir()
    output_path = os.path.join(output_dir, OUTPUT_JSON)

    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"✅ Сохранено в {output_path}")

def save_csv() -> None:
    """Сохраняет результаты в CSV, разделяя по n-gramm."""
    output_dir = get_output_dir()

    # Группируем n-gramm по количеству слов
    ngrams_by_length = {1: [], 2: [], 3: [], 4: [], 5: [], 6: []}

    for ngram, data in sorted(
        ngram_stats.items(),
        key=lambda x: x[1]['total'],
        reverse=True
    ):
        word_count = len(ngram.split())

        if word_count in ngrams_by_length:
            ids_count = len(data['ids'])
            total_count = data['total']
            avg_count = total_count / ids_count if ids_count > 0 else 0

            ngrams_by_length[word_count].append({
                'Фраза': ngram,
                'Count Pages': ids_count,
                'Count Total': total_count,
                'Среднее': round(avg_count, 2)
            })

    # Сохраняем каждый n-gramm в отдельный файл
    for n in range(1, 7):
        filename = f'{n}-gram.csv'
        output_path = os.path.join(output_dir, filename)

        if ngrams_by_length[n]:
            with open(output_path, 'w', encoding='utf-8-sig', newline='') as f:
                writer = csv.DictWriter(f, fieldnames=['Фраза', 'Count Pages', 'Count Total', 'Среднее'])
                writer.writeheader()
                writer.writerows(ngrams_by_length[n])

            print(f"✅ {filename}: {len(ngrams_by_length[n]):,} фраз → {output_path}")
        else:
            print(f"⚠️  {filename}: нет данных")

# =============================================================================
# ГЛАВНАЯ ФУНКЦИЯ
# =============================================================================

def main():
    """Главная функция."""
    # Парсинг аргументов командной строки
    parser = argparse.ArgumentParser(
        description='Выгрузка N-gramm из MySQL базы данных',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
Примеры использования:
  python ngram_mysql.py              # Выгрузить все данные из всех таблиц
  python ngram_mysql.py -name        # Выгрузить только shop_product.name
        '''
    )

    parser.add_argument(
        '-name', '--names-only',
        action='store_true',
        help='Выгрузить только shop_product.name (имена товаров)'
    )

    args = parser.parse_args()

    print("=" * 60)
    if args.names_only:
        print("🚀 ВЫГРУЗКА N-GRAMM (ТОЛЬКО SHOP_PRODUCT.NAME)")
    else:
        print("🚀 ВЫГРУЗКА N-GRAMM ИЗ MYSQL БАЗЫ ДАННЫХ")
    print("=" * 60)

    # Инициализация
    init_stop_words()
    load_custom_stop_words()

    # Подключение к MySQL
    try:
        connection = connect_to_mysql()
    except Exception as e:
        print(f"❌ {e}")
        print("\n⚠️  Убедитесь, что файл .env содержит:")
        print("   DB_HOST=localhost")
        print("   DB_PORT=3306")
        print("   DB_USER=your_user")
        print("   DB_PASSWORD=your_password")
        print("   DB_NAME=your_base")
        return

    # Загрузка данных из всех таблиц
    print("\n📊 Загрузка данных из таблиц:")
    print("-" * 60)

    all_records = []

    try:
        if args.names_only:
            # Только shop_product.name
            all_records.extend(fetch_products_names_only(connection))
        else:
            # Все таблицы
            all_records.extend(fetch_products(connection))
            all_records.extend(fetch_blog_posts(connection))
            all_records.extend(fetch_categories(connection))
            all_records.extend(fetch_brands(connection))
            all_records.extend(fetch_tags(connection))

    except Error as e:
        print(f"❌ Ошибка при загрузке данных: {e}")
        connection.close()
        return

    connection.close()

    print(f"\n✅ Всего загружено записей: {len(all_records)}")

    # Обработка данных
    print("\n🔍 Генерация N-gramm:")
    print("-" * 60)

    process_records(all_records)

    print(f"\n🔤 Уникальных N-gramm: {len(ngram_stats)}")

    # Сохранение результатов
    print("\n💾 Сохранение результатов:")
    print("-" * 60)

    save_json()
    save_csv()

    # Статистика
    print("\n" + "=" * 60)
    print("📊 ФИНАЛЬНАЯ СТАТИСТИКА")
    print("=" * 60)
    print(f"✅ Обработано записей: {len(all_records)}")
    print(f"🔤 Уникальных N-gramm: {len(ngram_stats)}")

    print("\n🏆 TOP-20 N-GRAMM:")
    top_ngrams = sorted(ngram_stats.items(), key=lambda x: x[1]['total'], reverse=True)[:20]
    for ngram, data in top_ngrams:
        print(f"  {ngram}: {data['total']} ({len(data['ids'])} ист.)")

    # Показать путь к папке с результатами
    output_dir = get_output_dir()
    print(f"\n📁 Папка с результатами: {output_dir}")

    print("\n✅ Выгрузка завершена!")

if __name__ == '__main__':
    main()
