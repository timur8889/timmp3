import telebot
from telebot import types
import sqlite3
import datetime
import os
import logging
import re
import shutil
import time
import decimal
import json
import hashlib
import threading
import asyncio
import requests
import pandas as pd
import io
import tempfile
from typing import List, Tuple, Optional, Dict, Any, Callable
from dotenv import load_dotenv
from functools import lru_cache, wraps
from threading import Lock, Thread, Timer, RLock
from collections import defaultdict, deque
import math
from contextlib import contextmanager
import pickle
import base64
from abc import ABC, abstractmethod
import smtplib
from email.mime.text import MimeText
from email.mime.multipart import MimeMultipart
import warnings
import psutil
import gc

# Загрузка переменных окружения
load_dotenv()

# =============================================================================
# РАСШИРЕННАЯ КОНФИГУРАЦИЯ
# =============================================================================

class DatabaseConfig:
    POOL_SIZE = 10
    CONNECTION_TIMEOUT = 30
    RETRY_ATTEMPTS = 3
    QUERY_TIMEOUT = 60
    WAL_MODE = True
    FOREIGN_KEYS = True

class BotConfig:
    MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB
    SUPPORTED_LANGUAGES = ['ru', 'en']
    TIMEZONE = 'Europe/Moscow'
    MAX_MESSAGE_LENGTH = 4096
    RATE_LIMIT_PER_USER = 10  # сообщений в минуту
    SESSION_TIMEOUT = 30 * 60  # 30 минут

class SecurityConfig:
    ADMIN_IDS = [int(x.strip()) for x in os.getenv('ADMIN_IDS', '').split(',') if x.strip()]
    ENCRYPTION_KEY = os.getenv('ENCRYPTION_KEY', 'default-secret-key')
    ALLOWED_FILE_TYPES = ['.pdf', '.xlsx', '.xls', '.doc', '.docx', '.jpg', '.png']
    MAX_LOGIN_ATTEMPTS = 5
    PASSWORD_MIN_LENGTH = 8

class ExternalAPIConfig:
    ENABLED_APIS = ['excel_export', 'email_notifications', 'webhook']
    EXCEL_EXPORT_PATH = 'exports'
    EMAIL_SMTP_SERVER = os.getenv('SMTP_SERVER', 'smtp.gmail.com')
    EMAIL_SMTP_PORT = int(os.getenv('SMTP_PORT', 587))
    EMAIL_USERNAME = os.getenv('EMAIL_USER')
    EMAIL_PASSWORD = os.getenv('EMAIL_PASSWORD')
    WEBHOOK_URL = os.getenv('WEBHOOK_URL', '')

class AnalyticsConfig:
    ENABLE_PREDICTIONS = True
    FORECAST_DAYS = 30
    RISK_THRESHOLD = 0.8
    COST_OPTIMIZATION_ENABLED = True

# Основной класс конфигурации
class EnhancedConfig:
    DB_PATH = 'construction_stats.db'
    BACKUP_DIR = 'backups'
    LOGS_DIR = 'logs'
    FILES_DIR = 'uploads'
    EXPORTS_DIR = 'exports'
    
    DEFAULT_DATE_FORMAT = '%Y-%m-%d'
    DATETIME_FORMAT = '%Y-%m-%d %H:%M:%S'
    BACKUP_INTERVAL = 24 * 60 * 60  # 24 часа
    STATE_TIMEOUT = 300  # 5 минут
    CACHE_TTL = 300  # 5 минут
    MAX_BACKUP_FILES = 10
    MAX_RECORDS_PER_PAGE = 5
    
    # Интеграция специализированных конфигураций
    DATABASE = DatabaseConfig()
    BOT = BotConfig()
    SECURITY = SecurityConfig()
    EXTERNAL_API = ExternalAPIConfig()
    ANALYTICS = AnalyticsConfig()
    
    @classmethod
    def validate_config(cls):
        """Расширенная валидация конфигурации"""
        required_env_vars = ['BOT_TOKEN']
        missing = [var for var in required_env_vars if not os.getenv(var)]
        if missing:
            raise ValueError(f"Missing required environment variables: {missing}")
        
        # Создание всех необходимых директорий
        directories = [cls.BACKUP_DIR, cls.LOGS_DIR, cls.FILES_DIR, cls.EXPORTS_DIR]
        for directory in directories:
            os.makedirs(directory, exist_ok=True)
        
        # Проверка прав доступа к директориям
        for directory in directories:
            if not os.access(directory, os.W_OK):
                raise PermissionError(f"No write access to directory: {directory}")
        
        logger.info("Enhanced configuration validated successfully")

# =============================================================================
# СИСТЕМА ОШИБОК И ИСКЛЮЧЕНИЙ
# =============================================================================

class BotException(Exception):
    """Базовое исключение для бота"""
    pass

class ValidationError(BotException):
    """Ошибка валидации данных"""
    pass

class DatabaseError(BotException):
    """Ошибка базы данных"""
    pass

class BusinessLogicError(BotException):
    """Ошибка бизнес-логики"""
    pass

class SecurityError(BotException):
    """Ошибка безопасности"""
    pass

class ExternalAPIError(BotException):
    """Ошибка внешнего API"""
    pass

# =============================================================================
# СИСТЕМА ПЛАГИНОВ
# =============================================================================

class Plugin(ABC):
    """Абстрактный базовый класс для плагинов"""
    
    @abstractmethod
    def initialize(self):
        """Инициализация плагина"""
        pass
    
    @abstractmethod
    def cleanup(self):
        """Очистка ресурсов плагина"""
        pass

class AnalyticsPlugin(Plugin):
    """Плагин аналитики"""
    
    def initialize(self):
        logger.info("AnalyticsPlugin initialized")
    
    def cleanup(self):
        logger.info("AnalyticsPlugin cleaned up")
    
    def pre_save_hook(self, data: Dict) -> Dict:
        """Хук перед сохранением данных"""
        # Можно добавить предобработку данных
        return data
    
    def post_save_hook(self, data: Dict):
        """Хук после сохранения данных"""
        # Можно запустить анализ после сохранения
        pass

class NotificationPlugin(Plugin):
    """Плагин уведомлений"""
    
    def initialize(self):
        logger.info("NotificationPlugin initialized")
    
    def cleanup(self):
        logger.info("NotificationPlugin cleaned up")
    
    def before_notification(self, message: str) -> str:
        """Хук перед отправкой уведомления"""
        return message
    
    def after_notification(self, success: bool):
        """Хук после отправки уведомления"""
        pass

class PluginManager:
    """Менеджер плагинов для расширяемости"""
    
    def __init__(self):
        self.plugins = {}
        self.hooks = defaultdict(list)
    
    def register_plugin(self, name: str, plugin: Plugin):
        """Регистрация плагина"""
        self.plugins[name] = plugin
        plugin.initialize()
        logger.info(f"Plugin registered: {name}")
    
    def unregister_plugin(self, name: str):
        """Удаление плагина"""
        if name in self.plugins:
            self.plugins[name].cleanup()
            del self.plugins[name]
            logger.info(f"Plugin unregistered: {name}")
    
    def register_hook(self, hook_name: str, plugin_name: str, method_name: str):
        """Регистрация хука"""
        if plugin_name in self.plugins:
            plugin = self.plugins[plugin_name]
            if hasattr(plugin, method_name):
                self.hooks[hook_name].append(getattr(plugin, method_name))
    
    def execute_hook(self, hook_name: str, *args, **kwargs):
        """Выполнение хуков"""
        results = []
        for hook in self.hooks.get(hook_name, []):
            try:
                result = hook(*args, **kwargs)
                results.append(result)
            except Exception as e:
                logger.error(f"Hook {hook_name} error: {e}")
        return results

# =============================================================================
# ВНЕШНИЕ API И ИНТЕГРАЦИИ
# =============================================================================

class ExternalAPIManager:
    """Менеджер внешних API и интеграций"""
    
    def __init__(self, db_manager):
        self.db = db_manager
        self.export_formats = ['excel', 'csv', 'json', 'pdf']
    
    async def sync_with_external_system(self, system_name: str, data: Dict) -> bool:
        """Синхронизация с внешними системами"""
        try:
            if system_name == 'crm':
                return await self._sync_with_crm(data)
            elif system_name == 'erp':
                return await self._sync_with_erp(data)
            else:
                logger.warning(f"Unknown external system: {system_name}")
                return False
        except Exception as e:
            logger.error(f"External sync error: {e}")
            raise ExternalAPIError(f"Sync failed: {e}")
    
    async def _sync_with_crm(self, data: Dict) -> bool:
        """Синхронизация с CRM системой"""
        # Заглушка для интеграции с CRM
        logger.info(f"Syncing with CRM: {data}")
        await asyncio.sleep(0.1)  # Имитация работы
        return True
    
    async def _sync_with_erp(self, data: Dict) -> bool:
        """Синхронизация с ERP системой"""
        # Заглушка для интеграции с ERP
        logger.info(f"Syncing with ERP: {data}")
        await asyncio.sleep(0.1)
        return True
    
    def export_to_excel(self, data: List[Dict], filename: str) -> str:
        """Экспорт данных в Excel"""
        try:
            os.makedirs(EnhancedConfig.EXPORTS_DIR, exist_ok=True)
            filepath = os.path.join(EnhancedConfig.EXPORTS_DIR, f"{filename}.xlsx")
            
            df = pd.DataFrame(data)
            with pd.ExcelWriter(filepath, engine='openpyxl') as writer:
                df.to_excel(writer, sheet_name='Data', index=False)
            
            logger.info(f"Data exported to Excel: {filepath}")
            return filepath
        except Exception as e:
            logger.error(f"Excel export error: {e}")
            raise ExternalAPIError(f"Excel export failed: {e}")
    
    def generate_pdf_report(self, report_data: Dict) -> str:
        """Генерация PDF отчета"""
        try:
            # Заглушка для генерации PDF
            # В реальной реализации можно использовать reportlab или weasyprint
            filepath = os.path.join(EnhancedConfig.EXPORTS_DIR, f"report_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf")
            
            with open(filepath, 'w') as f:
                f.write("PDF Report\n")
                f.write("==========\n\n")
                f.write(f"Generated: {datetime.datetime.now()}\n")
                f.write(f"Data: {json.dumps(report_data, indent=2)}\n")
            
            logger.info(f"PDF report generated: {filepath}")
            return filepath
        except Exception as e:
            logger.error(f"PDF generation error: {e}")
            raise ExternalAPIError(f"PDF generation failed: {e}")
    
    def send_email_report(self, recipient: str, subject: str, content: str, attachment_path: str = None) -> bool:
        """Отправка отчета по email"""
        try:
            if not all([ExternalAPIConfig.EMAIL_USERNAME, ExternalAPIConfig.EMAIL_PASSWORD]):
                logger.warning("Email credentials not configured")
                return False
            
            msg = MimeMultipart()
            msg['From'] = ExternalAPIConfig.EMAIL_USERNAME
            msg['To'] = recipient
            msg['Subject'] = subject
            
            msg.attach(MimeText(content, 'plain'))
            
            if attachment_path and os.path.exists(attachment_path):
                with open(attachment_path, "rb") as attachment:
                    part = MimeText(attachment.read(), 'base64')
                    part['Content-Disposition'] = f'attachment; filename="{os.path.basename(attachment_path)}"'
                    msg.attach(part)
            
            server = smtplib.SMTP(ExternalAPIConfig.EMAIL_SMTP_SERVER, ExternalAPIConfig.EMAIL_SMTP_PORT)
            server.starttls()
            server.login(ExternalAPIConfig.EMAIL_USERNAME, ExternalAPIConfig.EMAIL_PASSWORD)
            server.send_message(msg)
            server.quit()
            
            logger.info(f"Email sent to {recipient}")
            return True
        except Exception as e:
            logger.error(f"Email sending error: {e}")
            return False

# =============================================================================
# ПРОДВИНУТАЯ АНАЛИТИКА И ML
# =============================================================================

class Recommendation:
    """Класс рекомендации"""
    
    def __init__(self, title: str, description: str, priority: str, impact: float):
        self.title = title
        self.description = description
        self.priority = priority  # 'high', 'medium', 'low'
        self.impact = impact  # Ожидаемый эффект (0-1)
    
    def to_dict(self):
        return {
            'title': self.title,
            'description': self.description,
            'priority': self.priority,
            'impact': self.impact
        }

class Forecast:
    """Класс прогноза"""
    
    def __init__(self, predicted_cost: float, confidence: float, risks: List[str]):
        self.predicted_cost = predicted_cost
        self.confidence = confidence
        self.risks = risks
    
    def to_dict(self):
        return {
            'predicted_cost': self.predicted_cost,
            'confidence': self.confidence,
            'risks': self.risks
        }

class AnalyticsEngine:
    """Движок аналитики с ML-функциями"""
    
    def __init__(self, db_manager):
        self.db = db_manager
        self.model_cache = {}
    
    def predict_budget_risks(self, object_id: int) -> Dict[str, Any]:
        """Предсказание рисков бюджета"""
        try:
            # Получаем исторические данные по объекту
            history = self.db.execute_query('''
                SELECT date, total_cost FROM materials WHERE object_id = ?
                UNION ALL
                SELECT date, total_salary FROM salaries WHERE object_id = ?
                ORDER BY date
            ''', (object_id, object_id))
            
            if not history:
                return {'risk_level': 'low', 'message': 'Недостаточно данных для анализа'}
            
            # Простой алгоритм оценки рисков
            total_spent = sum(item[1] for item in history)
            budget_info = self.db.execute_query(
                'SELECT budget FROM objects WHERE id = ?', 
                (object_id,)
            )
            
            if not budget_info or not budget_info[0][0]:
                return {'risk_level': 'medium', 'message': 'Бюджет не установлен'}
            
            budget = budget_info[0][0]
            usage_ratio = total_spent / budget if budget > 0 else 0
            
            # Анализ тренда расходов
            recent_spending = self._analyze_spending_trend(history)
            
            risk_level = 'low'
            if usage_ratio > 0.9:
                risk_level = 'critical'
            elif usage_ratio > 0.7:
                risk_level = 'high'
            elif usage_ratio > 0.5 and recent_spending > 1.5:
                risk_level = 'medium'
            
            return {
                'risk_level': risk_level,
                'current_usage': usage_ratio,
                'total_spent': total_spent,
                'budget_remaining': budget - total_spent,
                'spending_trend': recent_spending
            }
            
        except Exception as e:
            logger.error(f"Budget risk prediction error: {e}")
            return {'risk_level': 'unknown', 'message': f'Ошибка анализа: {e}'}
    
    def _analyze_spending_trend(self, history: List) -> float:
        """Анализ тренда расходов"""
        if len(history) < 2:
            return 1.0
        
        # Разделяем данные на две половины и сравниваем средние расходы
        mid = len(history) // 2
        first_half = [item[1] for item in history[:mid]]
        second_half = [item[1] for item in history[mid:]]
        
        avg_first = sum(first_half) / len(first_half)
        avg_second = sum(second_half) / len(second_half)
        
        return avg_second / avg_first if avg_first > 0 else 1.0
    
    def optimize_costs(self, object_id: int) -> List[Recommendation]:
        """Генерация рекомендаций по оптимизации затрат"""
        recommendations = []
        
        try:
            # Анализ материалов
            materials = self.db.execute_query('''
                SELECT material_name, SUM(total_cost) as total, AVG(price_per_unit) as avg_price
                FROM materials 
                WHERE object_id = ?
                GROUP BY material_name
                ORDER BY total DESC
            ''', (object_id,))
            
            for material in materials:
                material_name, total_cost, avg_price = material
                
                # Рекомендация по поиску альтернативных поставщиков
                similar_materials = self.db.execute_query('''
                    SELECT material_name, AVG(price_per_unit) as comp_price
                    FROM materials 
                    WHERE material_name LIKE ? AND object_id != ?
                    GROUP BY material_name
                ''', (f"%{material_name}%", object_id))
                
                for comp_material in similar_materials:
                    comp_name, comp_price = comp_material
                    if comp_price and avg_price and comp_price < avg_price * 0.8:
                        recommendations.append(Recommendation(
                            title="Экономия на материалах",
                            description=f"Рассмотрите {comp_name} как альтернативу {material_name}. Возможная экономия: {avg_price - comp_price:.2f} руб./ед.",
                            priority="medium",
                            impact=0.3
                        ))
            
            # Анализ зарплат
            salaries = self.db.execute_query('''
                SELECT position, AVG(hourly_rate) as avg_rate, SUM(hours_worked) as total_hours
                FROM salaries 
                WHERE object_id = ?
                GROUP BY position
            ''', (object_id,))
            
            for salary in salaries:
                position, avg_rate, total_hours = salary
                
                # Рекомендация по оптимизации рабочего времени
                if total_hours > 160:  # Более 1 месяца работы
                    recommendations.append(Recommendation(
                        title="Оптимизация рабочего времени",
                        description=f"Позиция {position} имеет большой объем часов ({total_hours}). Рассмотрите оптимизацию процессов.",
                        priority="low",
                        impact=0.2
                    ))
            
            return sorted(recommendations, key=lambda x: x.impact, reverse=True)[:5]  # Топ-5 рекомендаций
            
        except Exception as e:
            logger.error(f"Cost optimization error: {e}")
            return [Recommendation(
                title="Ошибка анализа",
                description=f"Не удалось сгенерировать рекомендации: {e}",
                priority="low",
                impact=0.0
            )]
    
    def generate_forecast(self, object_id: int) -> Forecast:
        """Генерация прогноза по проекту"""
        try:
            # Простой алгоритм прогнозирования на основе исторических данных
            history = self.db.execute_query('''
                SELECT date, total_cost FROM materials WHERE object_id = ?
                UNION ALL
                SELECT date, total_salary FROM salaries WHERE object_id = ?
                ORDER BY date
            ''', (object_id, object_id))
            
            if not history:
                return Forecast(0, 0.0, ["Недостаточно данных для прогноза"])
            
            # Расчет среднемесячных расходов
            monthly_data = defaultdict(float)
            for date_str, cost in history:
                date = datetime.datetime.strptime(date_str, EnhancedConfig.DEFAULT_DATE_FORMAT)
                month_key = date.strftime('%Y-%m')
                monthly_data[month_key] += cost
            
            avg_monthly = sum(monthly_data.values()) / len(monthly_data)
            
            # Прогноз на следующий месяц
            predicted_cost = avg_monthly * 1.1  # +10% на рост
            
            # Анализ рисков
            risks = []
            if len(monthly_data) < 3:
                risks.append("Мало исторических данных для точного прогноза")
            if max(monthly_data.values()) > avg_monthly * 1.5:
                risks.append("Высокая волатильность расходов")
            
            confidence = min(0.9, len(monthly_data) / 10)  # Уверенность растет с количеством данных
            
            return Forecast(predicted_cost, confidence, risks)
            
        except Exception as e:
            logger.error(f"Forecast generation error: {e}")
            return Forecast(0, 0.0, [f"Ошибка прогнозирования: {e}"])

# =============================================================================
# WEBHOOK И ИНТЕГРАЦИЯ С ВЕБ-ПАНЕЛЬЮ
# =============================================================================

class WebhookManager:
    """Менеджер вебхуков для интеграции с веб-панелью"""
    
    def __init__(self):
        self.webhooks = []
        self.session = requests.Session()
        self.session.timeout = 10
    
    def add_webhook(self, url: str, secret: str = None, events: List[str] = None):
        """Добавление вебхука"""
        self.webhooks.append({
            'url': url,
            'secret': secret,
            'events': events or ['all'],
            'active': True
        })
        logger.info(f"Webhook added: {url}")
    
    async def send_webhook(self, event_type: str, data: Dict):
        """Отправка события на вебхуки"""
        if not self.webhooks:
            return
        
        payload = {
            'event_type': event_type,
            'data': data,
            'timestamp': datetime.datetime.now().isoformat(),
            'version': '1.0'
        }
        
        for webhook in self.webhooks:
            if not webhook['active']:
                continue
            
            if 'all' not in webhook['events'] and event_type not in webhook['events']:
                continue
            
            try:
                headers = {'Content-Type': 'application/json'}
                if webhook['secret']:
                    headers['X-Webhook-Signature'] = self._sign_payload(payload, webhook['secret'])
                
                response = await asyncio.get_event_loop().run_in_executor(
                    None, 
                    lambda: self.session.post(
                        webhook['url'], 
                        json=payload, 
                        headers=headers,
                        timeout=10
                    )
                )
                
                if response.status_code == 200:
                    logger.info(f"Webhook sent successfully: {event_type}")
                else:
                    logger.warning(f"Webhook returned status {response.status_code}: {event_type}")
                    
            except Exception as e:
                logger.error(f"Webhook sending error: {e}")
    
    def _sign_payload(self, payload: Dict, secret: str) -> str:
        """Подпись payload для безопасности"""
        payload_str = json.dumps(payload, sort_keys=True)
        return hashlib.sha256(f"{payload_str}{secret}".encode()).hexdigest()
    
    def test_webhook(self, webhook_url: str) -> bool:
        """Тестирование вебхука"""
        try:
            response = self.session.get(webhook_url, timeout=5)
            return response.status_code == 200
        except Exception as e:
            logger.error(f"Webhook test failed: {e}")
            return False

# =============================================================================
# ГЕНЕРАТОР ОТЧЕТОВ
# =============================================================================

class ReportGenerator:
    """Продвинутый генератор отчетов"""
    
    def __init__(self, db_manager):
        self.db = db_manager
    
    def generate_comprehensive_report(self, object_id: int) -> Dict[str, Any]:
        """Генерация комплексного отчета по объекту"""
        try:
            # Основная информация об объекте
            object_info = self.db.execute_query(
                'SELECT name, address, start_date, end_date, budget, status FROM objects WHERE id = ?', 
                (object_id,)
            )[0]
            
            # Финансовая статистика
            financial_stats = self._get_financial_stats(object_id)
            
            # Анализ временной шкалы
            timeline_analysis = self._analyze_timeline(object_id, object_info)
            
            # Анализ рисков
            risk_analysis = self._analyze_risks(object_id, financial_stats)
            
            # Рекомендации
            recommendations = self._generate_recommendations(object_id, financial_stats)
            
            return {
                'object_info': {
                    'name': object_info[0],
                    'address': object_info[1],
                    'start_date': object_info[2],
                    'end_date': object_info[3],
                    'budget': object_info[4],
                    'status': object_info[5]
                },
                'financial_analysis': financial_stats,
                'timeline_analysis': timeline_analysis,
                'risk_analysis': risk_analysis,
                'recommendations': recommendations,
                'generated_at': datetime.datetime.now().isoformat(),
                'report_id': hashlib.md5(f"{object_id}_{datetime.datetime.now()}".encode()).hexdigest()[:8]
            }
            
        except Exception as e:
            logger.error(f"Comprehensive report generation error: {e}")
            raise BusinessLogicError(f"Report generation failed: {e}")
    
    def _get_financial_stats(self, object_id: int) -> Dict:
        """Получение финансовой статистики"""
        materials = self.db.execute_query('''
            SELECT SUM(total_cost), COUNT(*), AVG(price_per_unit)
            FROM materials WHERE object_id = ?
        ''', (object_id,))[0]
        
        salaries = self.db.execute_query('''
            SELECT SUM(total_salary), COUNT(*), AVG(hourly_rate), SUM(hours_worked)
            FROM salaries WHERE object_id = ?
        ''', (object_id,))[0]
        
        total_materials = materials[0] or 0
        total_salaries = salaries[0] or 0
        total_cost = total_materials + total_salaries
        
        return {
            'total_cost': total_cost,
            'materials_cost': total_materials,
            'salaries_cost': total_salaries,
            'materials_count': materials[1] or 0,
            'salaries_count': salaries[1] or 0,
            'avg_material_price': materials[2] or 0,
            'avg_hourly_rate': salaries[2] or 0,
            'total_hours_worked': salaries[3] or 0
        }
    
    def _analyze_timeline(self, object_id: int, object_info: Tuple) -> Dict:
        """Анализ временной шкалы"""
        timeline = {}
        
        if object_info[2]:  # start_date
            start_date = datetime.datetime.strptime(object_info[2], EnhancedConfig.DEFAULT_DATE_FORMAT)
            today = datetime.datetime.now()
            
            if object_info[3]:  # end_date
                end_date = datetime.datetime.strptime(object_info[3], EnhancedConfig.DEFAULT_DATE_FORMAT)
                total_days = (end_date - start_date).days
                days_passed = (today - start_date).days
                timeline['completion_percentage'] = min(100, (days_passed / total_days * 100)) if total_days > 0 else 0
                timeline['days_remaining'] = max(0, (end_date - today).days)
            else:
                timeline['days_passed'] = (today - start_date).days
        
        return timeline
    
    def _analyze_risks(self, object_id: int, financial_stats: Dict) -> Dict:
        """Анализ рисков"""
        risks = []
        
        # Риск превышения бюджета
        budget_info = self.db.execute_query(
            'SELECT budget FROM objects WHERE id = ?', 
            (object_id,)
        )
        
        if budget_info and budget_info[0][0]:
            budget = budget_info[0][0]
            usage = financial_stats['total_cost'] / budget if budget > 0 else 0
            
            if usage > 0.9:
                risks.append({'type': 'budget', 'level': 'critical', 'message': 'Бюджет почти исчерпан'})
            elif usage > 0.7:
                risks.append({'type': 'budget', 'level': 'high', 'message': 'Высокий риск превышения бюджета'})
            elif usage > 0.5:
                risks.append({'type': 'budget', 'level': 'medium', 'message': 'Средний риск превышения бюджета'})
        
        # Риск задержек
        timeline = self._analyze_timeline(object_id, 
            self.db.execute_query('SELECT name, address, start_date, end_date, budget, status FROM objects WHERE id = ?', (object_id,))[0]
        )
        
        if 'completion_percentage' in timeline and timeline['completion_percentage'] > 75:
            risks.append({'type': 'timeline', 'level': 'medium', 'message': 'Проект близок к завершению'})
        
        return {'risks': risks, 'total_risk_level': 'high' if any(r['level'] in ['critical', 'high'] for r in risks) else 'medium'}
    
    def _generate_recommendations(self, object_id: int, financial_stats: Dict) -> List[Dict]:
        """Генерация рекомендаций"""
        recommendations = []
        
        # Рекомендации на основе финансовых данных
        if financial_stats['materials_cost'] > financial_stats['salaries_cost'] * 2:
            recommendations.append({
                'type': 'cost_optimization',
                'priority': 'medium',
                'title': 'Оптимизация затрат на материалы',
                'description': 'Рассмотрите возможность пересмотра закупок материалов'
            })
        
        if financial_stats['total_hours_worked'] > 500:
            recommendations.append({
                'type': 'efficiency',
                'priority': 'low',
                'title': 'Анализ эффективности труда',
                'description': 'Большой объем рабочих часов. Проверьте эффективность процессов'
            })
        
        return recommendations
    
    def export_report(self, report_data: Dict, format: str = 'json') -> str:
        """Экспорт отчета в различные форматы"""
        try:
            timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
            
            if format == 'json':
                filename = f"report_{timestamp}.json"
                filepath = os.path.join(EnhancedConfig.EXPORTS_DIR, filename)
                with open(filepath, 'w', encoding='utf-8') as f:
                    json.dump(report_data, f, indent=2, ensure_ascii=False)
            
            elif format == 'excel':
                filename = f"report_{timestamp}.xlsx"
                filepath = os.path.join(EnhancedConfig.EXPORTS_DIR, filename)
                
                # Создаем Excel файл с несколькими листами
                with pd.ExcelWriter(filepath, engine='openpyxl') as writer:
                    # Лист с основной информацией
                    basic_info = pd.DataFrame([report_data['object_info']])
                    basic_info.to_excel(writer, sheet_name='Объект', index=False)
                    
                    # Лист с финансовой аналитикой
                    financial_data = pd.DataFrame([report_data['financial_analysis']])
                    financial_data.to_excel(writer, sheet_name='Финансы', index=False)
                    
                    # Лист с рекомендациями
                    if report_data['recommendations']:
                        rec_data = pd.DataFrame(report_data['recommendations'])
                        rec_data.to_excel(writer, sheet_name='Рекомендации', index=False)
            
            else:
                raise ValueError(f"Unsupported format: {format}")
            
            logger.info(f"Report exported: {filepath}")
            return filepath
            
        except Exception as e:
            logger.error(f"Report export error: {e}")
            raise ExternalAPIError(f"Report export failed: {e}")

# =============================================================================
# МОНИТОРИНГ ЗДОРОВЬЯ СИСТЕМЫ
# =============================================================================

class HealthChecker:
    """Проверка здоровья системы"""
    
    def __init__(self, db_manager, cache_manager):
        self.db = db_manager
        self.cache = cache_manager
        self.health_history = deque(maxlen=100)
    
    def check_system_health(self) -> Dict[str, Any]:
        """Комплексная проверка здоровья системы"""
        health_status = {
            'timestamp': datetime.datetime.now().isoformat(),
            'overall_status': 'healthy',
            'components': {},
            'metrics': {}
        }
        
        try:
            # Проверка базы данных
            db_health = self._check_database()
            health_status['components']['database'] = db_health
            
            # Проверка хранилища
            storage_health = self._check_storage()
            health_status['components']['storage'] = storage_health
            
            # Проверка памяти
            memory_health = self._check_memory()
            health_status['components']['memory'] = memory_health
            
            # Проверка производительности
            performance_health = self._check_performance()
            health_status['components']['performance'] = performance_health
            
            # Сбор метрик
            health_status['metrics'] = self._collect_metrics()
            
            # Определение общего статуса
            unhealthy_components = [
                comp for comp, status in health_status['components'].items() 
                if status['status'] != 'healthy'
            ]
            
            if unhealthy_components:
                health_status['overall_status'] = 'unhealthy'
                health_status['unhealthy_components'] = unhealthy_components
            
            # Сохраняем историю
            self.health_history.append(health_status)
            
            return health_status
            
        except Exception as e:
            logger.error(f"Health check error: {e}")
            return {
                'timestamp': datetime.datetime.now().isoformat(),
                'overall_status': 'error',
                'error': str(e)
            }
    
    def _check_database(self) -> Dict:
        """Проверка состояния базы данных"""
        try:
            start_time = time.time()
            
            # Проверяем соединение и основные запросы
            self.db.execute_query("SELECT 1")
            
            # Проверяем размер базы данных
            db_size = os.path.getsize(EnhancedConfig.DB_PATH) if os.path.exists(EnhancedConfig.DB_PATH) else 0
            
            # Проверяем количество таблиц
            tables = self.db.execute_query("SELECT name FROM sqlite_master WHERE type='table'")
            
            response_time = time.time() - start_time
            
            status = 'healthy'
            if response_time > 5:
                status = 'degraded'
            if db_size > 100 * 1024 * 1024:  # 100MB
                status = 'warning'
            
            return {
                'status': status,
                'response_time': response_time,
                'db_size_mb': db_size / 1024 / 1024,
                'table_count': len(tables),
                'message': 'Database is operational'
            }
            
        except Exception as e:
            return {
                'status': 'unhealthy',
                'error': str(e),
                'message': 'Database connection failed'
            }
    
    def _check_storage(self) -> Dict:
        """Проверка состояния хранилища"""
        try:
            # Проверяем доступное место на диске
            disk_usage = psutil.disk_usage('.')
            free_percent = disk_usage.free / disk_usage.total * 100
            
            status = 'healthy'
            if free_percent < 10:
                status = 'critical'
            elif free_percent < 20:
                status = 'warning'
            
            return {
                'status': status,
                'total_gb': disk_usage.total / 1024 / 1024 / 1024,
                'free_gb': disk_usage.free / 1024 / 1024 / 1024,
                'free_percent': free_percent,
                'message': f'Storage: {free_percent:.1f}% free'
            }
            
        except Exception as e:
            return {
                'status': 'unhealthy',
                'error': str(e),
                'message': 'Storage check failed'
            }
    
    def _check_memory(self) -> Dict:
        """Проверка использования памяти"""
        try:
            memory = psutil.virtual_memory()
            memory_percent = memory.percent
            
            status = 'healthy'
            if memory_percent > 90:
                status = 'critical'
            elif memory_percent > 80:
                status = 'warning'
            
            return {
                'status': status,
                'used_percent': memory_percent,
                'total_gb': memory.total / 1024 / 1024 / 1024,
                'available_gb': memory.available / 1024 / 1024 / 1024,
                'message': f'Memory: {memory_percent:.1f}% used'
            }
            
        except Exception as e:
            return {
                'status': 'unhealthy',
                'error': str(e),
                'message': 'Memory check failed'
            }
    
    def _check_performance(self) -> Dict:
        """Проверка производительности"""
        try:
            # Проверяем загрузку CPU
            cpu_percent = psutil.cpu_percent(interval=1)
            
            # Проверяем нагрузку на систему
            load_avg = os.getloadavg() if hasattr(os, 'getloadavg') else [0, 0, 0]
            
            status = 'healthy'
            if cpu_percent > 90:
                status = 'critical'
            elif cpu_percent > 70:
                status = 'warning'
            
            return {
                'status': status,
                'cpu_percent': cpu_percent,
                'load_avg': load_avg,
                'message': f'CPU: {cpu_percent:.1f}% used'
            }
            
        except Exception as e:
            return {
                'status': 'unhealthy',
                'error': str(e),
                'message': 'Performance check failed'
            }
    
    def _collect_metrics(self) -> Dict:
        """Сбор системных метрик"""
        return {
            'timestamp': datetime.datetime.now().isoformat(),
            'python_version': f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
            'process_memory_mb': psutil.Process().memory_info().rss / 1024 / 1024,
            'open_files': len(psutil.Process().open_files()),
            'thread_count': threading.active_count(),
            'gc_stats': gc.get_stats()
        }
    
    def get_health_history(self) -> List[Dict]:
        """Получение истории проверок здоровья"""
        return list(self.health_history)
    
    def generate_health_report(self) -> str:
        """Генерация отчета о здоровье системы"""
        current_health = self.check_system_health()
        
        report = f"""
🏥 ОТЧЕТ О СОСТОЯНИИ СИСТЕМЫ
📅 Сгенерирован: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

📊 ОБЩИЙ СТАТУС: {current_health['overall_status'].upper()}

КОМПОНЕНТЫ:
"""
        for component, status in current_health['components'].items():
            report += f"• {component.upper()}: {status['status']} - {status.get('message', 'N/A')}\n"
        
        report += f"""
📈 МЕТРИКИ:
• Память: {current_health['metrics'].get('process_memory_mb', 0):.1f} MB
• Потоки: {current_health['metrics'].get('thread_count', 0)}
• Файлы: {current_health['metrics'].get('open_files', 0)}
"""
        return report

# =============================================================================
# ОБРАБОТКА ФАЙЛОВ
# =============================================================================

class FileManager:
    """Менеджер обработки файлов"""
    
    def __init__(self):
        self.allowed_extensions = SecurityConfig.ALLOWED_FILE_TYPES
        self.max_file_size = BotConfig.MAX_FILE_SIZE
    
    def save_uploaded_file(self, file_content: bytes, filename: str, object_id: int = None) -> str:
        """Сохранение загруженного файла"""
        try:
            # Проверка расширения файла
            file_ext = os.path.splitext(filename)[1].lower()
            if file_ext not in self.allowed_extensions:
                raise ValidationError(f"Недопустимый тип файла: {file_ext}")
            
            # Проверка размера файла
            if len(file_content) > self.max_file_size:
                raise ValidationError(f"Файл слишком большой: {len(file_content)} bytes")
            
            # Создание директории для файлов
            files_dir = os.path.join(EnhancedConfig.FILES_DIR, str(object_id) if object_id else 'general')
            os.makedirs(files_dir, exist_ok=True)
            
            # Генерация безопасного имени файла
            safe_filename = self._generate_safe_filename(filename)
            filepath = os.path.join(files_dir, safe_filename)
            
            # Сохранение файла
            with open(filepath, 'wb') as f:
                f.write(file_content)
            
            logger.info(f"File saved: {filepath}")
            return filepath
            
        except Exception as e:
            logger.error(f"File save error: {e}")
            raise
    
    def _generate_safe_filename(self, filename: str) -> str:
        """Генерация безопасного имени файла"""
        name, ext = os.path.splitext(filename)
        safe_name = re.sub(r'[^\w\s-]', '', name)
        safe_name = re.sub(r'[-\s]+', '-', safe_name)
        timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
        return f"{safe_name}_{timestamp}{ext}"
    
    def get_file_info(self, filepath: str) -> Dict:
        """Получение информации о файле"""
        if not os.path.exists(filepath):
            raise FileNotFoundError(f"File not found: {filepath}")
        
        stat = os.stat(filepath)
        return {
            'filename': os.path.basename(filepath),
            'size': stat.st_size,
            'created': datetime.datetime.fromtimestamp(stat.st_ctime),
            'modified': datetime.datetime.fromtimestamp(stat.st_mtime),
            'path': filepath
        }
    
    def list_files(self, object_id: int = None) -> List[Dict]:
        """Список файлов для объекта"""
        files_dir = os.path.join(EnhancedConfig.FILES_DIR, str(object_id) if object_id else 'general')
        
        if not os.path.exists(files_dir):
            return []
        
        files = []
        for filename in os.listdir(files_dir):
            filepath = os.path.join(files_dir, filename)
            if os.path.isfile(filepath):
                files.append(self.get_file_info(filepath))
        
        return sorted(files, key=lambda x: x['modified'], reverse=True)
    
    def delete_file(self, filepath: str) -> bool:
        """Удаление файла"""
        try:
            if os.path.exists(filepath):
                os.remove(filepath)
                logger.info(f"File deleted: {filepath}")
                return True
            return False
        except Exception as e:
            logger.error(f"File deletion error: {e}")
            return False

# =============================================================================
# СИСТЕМА ПОИСКА
# =============================================================================

class SearchEngine:
    """Продвинутая система поиска"""
    
    def __init__(self, db_manager):
        self.db = db_manager
        self.search_index = {}
        self._build_index()
    
    def _build_index(self):
        """Построение поискового индекса"""
        # В реальной реализации здесь было бы построение полнотекстового индекса
        # Для демонстрации используем простой подход
        logger.info("Building search index...")
    
    def search_materials(self, query: str, filters: Dict = None) -> List[Dict]:
        """Поиск материалов"""
        try:
            sql = '''
                SELECT m.*, o.name as object_name 
                FROM materials m 
                JOIN objects o ON m.object_id = o.id 
                WHERE m.material_name LIKE ? OR m.notes LIKE ?
            '''
            params = [f'%{query}%', f'%{query}%']
            
            # Добавляем фильтры
            if filters:
                if 'category' in filters:
                    sql += ' AND m.category = ?'
                    params.append(filters['category'])
                if 'date_from' in filters:
                    sql += ' AND m.date >= ?'
                    params.append(filters['date_from'])
                if 'date_to' in filters:
                    sql += ' AND m.date <= ?'
                    params.append(filters['date_to'])
            
            sql += ' ORDER BY m.date DESC LIMIT 50'
            
            results = self.db.execute_query(sql, params)
            return [dict(row) for row in results]
            
        except Exception as e:
            logger.error(f"Materials search error: {e}")
            return []
    
    def search_objects(self, query: str) -> List[Dict]:
        """Поиск объектов"""
        try:
            results = self.db.execute_query('''
                SELECT * FROM objects 
                WHERE name LIKE ? OR address LIKE ? OR description LIKE ?
                ORDER BY name
            ''', [f'%{query}%', f'%{query}%', f'%{query}%'])
            
            return [dict(row) for row in results]
        except Exception as e:
            logger.error(f"Objects search error: {e}")
            return []
    
    def fuzzy_search_workers(self, query: str) -> List[Dict]:
        """Нечеткий поиск работников"""
        try:
            results = self.db.execute_query('''
                SELECT DISTINCT worker_name, position 
                FROM salaries 
                WHERE worker_name LIKE ? 
                ORDER BY worker_name
            ''', [f'%{query}%'])
            
            return [dict(row) for row in results]
        except Exception as e:
            logger.error(f"Workers search error: {e}")
            return []
    
    def advanced_search(self, search_params: Dict) -> Dict:
        """Продвинутый поиск с агрегацией"""
        results = {
            'materials': [],
            'objects': [],
            'workers': [],
            'total_results': 0
        }
        
        if 'materials_query' in search_params:
            results['materials'] = self.search_materials(
                search_params['materials_query'],
                search_params.get('filters', {})
            )
        
        if 'objects_query' in search_params:
            results['objects'] = self.search_objects(search_params['objects_query'])
        
        if 'workers_query' in search_params:
            results['workers'] = self.fuzzy_search_workers(search_params['workers_query'])
        
        results['total_results'] = len(results['materials']) + len(results['objects']) + len(results['workers'])
        
        return results

# =============================================================================
# СИСТЕМА ШАБЛОНОВ
# =============================================================================

class TemplateManager:
    """Менеджер шаблонов сообщений"""
    
    def __init__(self):
        self.templates = {
            'daily_report': self._daily_report_template,
            'budget_alert': self._budget_alert_template,
            'welcome': self._welcome_template,
            'health_report': self._health_report_template,
            'comprehensive_report': self._comprehensive_report_template
        }
    
    def render(self, template_name: str, **kwargs) -> str:
        """Рендеринг шаблона"""
        if template_name not in self.templates:
            raise ValueError(f"Unknown template: {template_name}")
        
        try:
            return self.templates[template_name](**kwargs)
        except Exception as e:
            logger.error(f"Template rendering error: {e}")
            return f"❌ Ошибка генерации шаблона: {template_name}"
    
    def _daily_report_template(self, **kwargs) -> str:
        """Шаблон ежедневного отчета"""
        return f"""
📊 ЕЖЕДНЕВНЫЙ ОТЧЕТ
📅 {kwargs.get('date', datetime.datetime.now().strftime('%d.%m.%Y'))}

📈 СТАТИСТИКА ЗА ДЕНЬ:
• 🏗️ Объектов с материалами: {kwargs.get('objects_with_materials', 0)}
• 👥 Объектов с выплатами: {kwargs.get('objects_with_salaries', 0)}
• 👷 Работников: {kwargs.get('workers_count', 0)}
• 📦 Материалы: {kwargs.get('materials_cost', 0):.2f} руб.
• 💵 Зарплаты: {kwargs.get('salaries_cost', 0):.2f} руб.
• 💰 Итого: {kwargs.get('daily_total', 0):.2f} руб.

📋 ОБЩАЯ СТАТИСТИКА:
• 🏗️ Активных объектов: {kwargs.get('total_objects', 0)}
• 📊 Общие расходы: {kwargs.get('total_expenses', 0):.2f} руб.
• 🗓️ За месяц: {kwargs.get('monthly_total', 0):.2f} руб.
"""
    
    def _budget_alert_template(self, **kwargs) -> str:
        """Шаблон предупреждения о бюджете"""
        return f"""
🚨 ПРЕДУПРЕЖДЕНИЕ О БЮДЖЕТЕ

🏗️ Объект: {kwargs.get('object_name', 'N/A')}
💸 Текущие расходы: {kwargs.get('current_usage', 0):.2f} руб.
📊 Бюджет: {kwargs.get('budget', 0):.2f} руб.
📈 Использовано: {kwargs.get('usage_percent', 0):.1f}%

⚠️ Статус: {kwargs.get('alert_level', 'warning')}
💡 Рекомендация: {kwargs.get('recommendation', 'Пересмотрите расходы')}
"""
    
    def _welcome_template(self, **kwargs) -> str:
        """Шаблон приветственного сообщения"""
        return f"""
🏗️ Добро пожаловать в Construction Manager Bot!

👋 Привет, {kwargs.get('user_name', 'друг')}!

✨ Возможности бота:
• 📍 Учет объектов строительства
• 📦 Ведение расходов на материалов
• 👥 Учет зарплат сотрудников  
• 📊 Полная статистика по проектам
• 🤖 AI-аналитика и прогнозы
• 📤 Экспорт данных в удобном формате
• 🔔 Умные уведомления и отчеты

🎯 Выберите раздел в меню ниже 👇
"""
    
    def _health_report_template(self, **kwargs) -> str:
        """Шаблон отчета о здоровье системы"""
        return f"""
🏥 ОТЧЕТ О СОСТОЯНИИ СИСТЕМЫ
📅 {kwargs.get('timestamp', datetime.datetime.now().strftime('%d.%m.%Y %H:%M'))}

📊 ОБЩИЙ СТАТУС: {kwargs.get('overall_status', 'unknown').upper()}

🔍 КОМПОНЕНТЫ:
{kwargs.get('components_summary', 'N/A')}

📈 МЕТРИКИ:
{kwargs.get('metrics_summary', 'N/A')}

💡 РЕКОМЕНДАЦИИ:
{kwargs.get('recommendations', 'N/A')}
"""
    
    def _comprehensive_report_template(self, **kwargs) -> str:
        """Шаблон комплексного отчета"""
        return f"""
📊 КОМПЛЕКСНЫЙ ОТЧЕТ
🏗️ Объект: {kwargs.get('object_name', 'N/A')}
📅 Период: {kwargs.get('period', 'N/A')}

💵 ФИНАНСЫ:
• Общие расходы: {kwargs.get('total_cost', 0):.2f} руб.
• Материалы: {kwargs.get('materials_cost', 0):.2f} руб.
• Зарплаты: {kwargs.get('salaries_cost', 0):.2f} руб.

📈 АНАЛИТИКА:
{kwargs.get('analysis_summary', 'N/A')}

⚠️ РИСКИ:
{kwargs.get('risks_summary', 'Нет значительных рисков')}

💡 РЕКОМЕНДАЦИИ:
{kwargs.get('recommendations_summary', 'Нет рекомендаций')}
"""

# =============================================================================
# ИНТЕГРАЦИЯ ВСЕХ КОМПОНЕНТОВ В ОСНОВНОЙ КОД
# =============================================================================

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(f'{EnhancedConfig.LOGS_DIR}/bot.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Безопасное получение токена
BOT_TOKEN = os.getenv('BOT_TOKEN')
if not BOT_TOKEN:
    logger.error("BOT_TOKEN not found in environment variables")
    exit(1)

# Инициализация бота
bot = telebot.TeleBot(BOT_TOKEN)

# Инициализация всех улучшенных менеджеров
user_state_manager = UserStateManager()
db = DatabaseManager()
smart_cache = SmartCache()
pagination_system = PaginationSystem()
notification_manager = EnhancedNotificationManager(bot, db)
background_tasks = BackgroundTasks()

# Инициализация новых систем
plugin_manager = PluginManager()
api_manager = ExternalAPIManager(db)
analytics_engine = AnalyticsEngine(db)
webhook_manager = WebhookManager()
report_generator = ReportGenerator(db)
health_checker = HealthChecker(db, smart_cache)
file_manager = FileManager()
search_engine = SearchEngine(db)
template_manager = TemplateManager()

# Регистрация плагинов
plugin_manager.register_plugin('analytics', AnalyticsPlugin())
plugin_manager.register_plugin('notifications', NotificationPlugin())

# =============================================================================
# ОБНОВЛЕННЫЕ ОБРАБОТЧИКИ С ИСПОЛЬЗОВАНИЕМ НОВЫХ СИСТЕМ
# =============================================================================

@bot.message_handler(commands=['health'])
@safe_execute()
@admin_required
@track_metrics('health_command')
def health_command(message):
    """Проверка здоровья системы"""
    health_status = health_checker.check_system_health()
    health_report = health_checker.generate_health_report()
    
    bot.send_message(message.chat.id, health_report)
    
    # Детальный отчет для админов
    if health_status['overall_status'] != 'healthy':
        detailed_report = f"Детальный статус:\n{json.dumps(health_status, indent=2, ensure_ascii=False)}"
        bot.send_message(message.chat.id, detailed_report)

@bot.message_handler(commands=['analyze'])
@safe_execute()
@track_metrics('analyze_command')
def analyze_command(message):
    """AI-анализ объекта"""
    try:
        objects = db.execute_query('SELECT id, name FROM objects WHERE status = "active"')
        if not objects:
            bot.send_message(message.chat.id, "❌ Нет активных объектов для анализа")
            return
        
        markup = types.InlineKeyboardMarkup()
        for obj in objects:
            markup.add(types.InlineKeyboardButton(
                obj[1], 
                callback_data=f"analyze_object_{obj[0]}"
            ))
        
        bot.send_message(message.chat.id, "🏗️ Выберите объект для анализа:", reply_markup=markup)
        
    except Exception as e:
        logger.error(f"Analyze command error: {e}")
        bot.send_message(message.chat.id, "❌ Ошибка при запуске анализа")

@bot.callback_query_handler(func=lambda call: call.data.startswith('analyze_object_'))
def handle_analyze_object(call):
    """Обработка выбора объекта для анализа"""
    try:
        object_id = int(call.data.split('_')[2])
        
        # Получаем анализ рисков
        risk_analysis = analytics_engine.predict_budget_risks(object_id)
        
        # Получаем рекомендации
        recommendations = analytics_engine.optimize_costs(object_id)
        
        # Генерируем прогноз
        forecast = analytics_engine.generate_forecast(object_id)
        
        # Формируем отчет
        report = f"""
🤖 AI-АНАЛИЗ ОБЪЕКТА

📊 АНАЛИЗ РИСКОВ:
• Уровень риска: {risk_analysis.get('risk_level', 'unknown')}
• Использовано бюджета: {risk_analysis.get('current_usage', 0)*100:.1f}%
• Остаток бюджета: {risk_analysis.get('budget_remaining', 0):.2f} руб.

📈 ПРОГНОЗ:
• Предсказанные затраты: {forecast.predicted_cost:.2f} руб.
• Уверенность прогноза: {forecast.confidence*100:.1f}%
• Риски: {', '.join(forecast.risks) if forecast.risks else 'Нет'}

💡 РЕКОМЕНДАЦИИ:
"""
        for i, rec in enumerate(recommendations[:3], 1):
            report += f"{i}. {rec.title}\n   {rec.description}\n\n"
        
        bot.send_message(call.message.chat.id, report)
        bot.answer_callback_query(call.id, "Анализ завершен")
        
    except Exception as e:
        logger.error(f"Object analysis error: {e}")
        bot.send_message(call.message.chat.id, "❌ Ошибка при анализе объекта")
        bot.answer_callback_query(call.id, "Ошибка анализа")

@bot.message_handler(commands=['search'])
@safe_execute()
@track_metrics('search_command')
def search_command(message):
    """Расширенный поиск"""
    try:
        bot.send_message(
            message.chat.id,
            "🔍 Расширенный поиск\n\n"
            "Введите поисковый запрос в формате:\n"
            "• `материал:название` - поиск материалов\n"
            "• `объект:название` - поиск объектов\n" 
            "• `работник:имя` - поиск работников\n"
            "• `общий запрос` - поиск по всем данным"
        )
        user_state_manager.set_state(
            message.from_user.id, 
            'waiting_search_query'
        )
    except Exception as e:
        logger.error(f"Search command error: {e}")
        bot.send_message(message.chat.id, "❌ Ошибка запуска поиска")

@bot.message_handler(func=lambda message: user_state_manager.get_state(message.from_user.id) and 
                   user_state_manager.get_state(message.from_user.id)['state'] == 'waiting_search_query')
def handle_search_query(message):
    """Обработка поискового запроса"""
    try:
        user_state_manager.clear_state(message.from_user.id)
        query = message.text.strip()
        
        if query.startswith('материал:'):
            materials = search_engine.search_materials(query.replace('материал:', '').strip())
            response = f"📦 Найдено материалов: {len(materials)}\n\n"
            for material in materials[:5]:
                response += f"• {material['material_name']} - {material['total_cost']} руб.\n"
        
        elif query.startswith('объект:'):
            objects = search_engine.search_objects(query.replace('объект:', '').strip())
            response = f"🏗️ Найдено объектов: {len(objects)}\n\n"
            for obj in objects[:5]:
                response += f"• {obj['name']} - {obj['address']}\n"
        
        elif query.startswith('работник:'):
            workers = search_engine.fuzzy_search_workers(query.replace('работник:', '').strip())
            response = f"👷 Найдено работников: {len(workers)}\n\n"
            for worker in workers[:5]:
                response += f"• {worker['worker_name']} - {worker['position']}\n"
        
        else:
            # Общий поиск
            results = search_engine.advanced_search({
                'materials_query': query,
                'objects_query': query,
                'workers_query': query
            })
            response = f"🔍 Результаты поиска '{query}':\n\n"
            response += f"📦 Материалы: {len(results['materials'])}\n"
            response += f"🏗️ Объекты: {len(results['objects'])}\n"
            response += f"👷 Работники: {len(results['workers'])}\n"
            response += f"📊 Всего: {results['total_results']}\n"
        
        bot.send_message(message.chat.id, response)
        
    except Exception as e:
        logger.error(f"Search handling error: {e}")
        bot.send_message(message.chat.id, "❌ Ошибка при выполнении поиска")

@bot.message_handler(commands=['report'])
@safe_execute()
@track_metrics('report_command')
def report_command(message):
    """Генерация комплексного отчета"""
    try:
        objects = db.execute_query('SELECT id, name FROM objects WHERE status = "active"')
        if not objects:
            bot.send_message(message.chat.id, "❌ Нет активных объектов для отчета")
            return
        
        markup = types.InlineKeyboardMarkup(row_width=1)
        for obj in objects:
            markup.add(types.InlineKeyboardButton(
                f"📊 {obj[1]}", 
                callback_data=f"report_object_{obj[0]}"
            ))
        
        bot.send_message(
            message.chat.id, 
            "📈 Генерация комплексного отчета\n\nВыберите объект:",
            reply_markup=markup
        )
        
    except Exception as e:
        logger.error(f"Report command error: {e}")
        bot.send_message(message.chat.id, "❌ Ошибка запуска генерации отчета")

@bot.callback_query_handler(func=lambda call: call.data.startswith('report_object_'))
def handle_report_generation(call):
    """Обработка генерации отчета"""
    try:
        object_id = int(call.data.split('_')[2])
        
        # Генерируем комплексный отчет
        report_data = report_generator.generate_comprehensive_report(object_id)
        
        # Экспортируем в Excel
        excel_file = report_generator.export_report(report_data, 'excel')
        
        # Отправляем файл пользователю
        with open(excel_file, 'rb') as f:
            bot.send_document(
                call.message.chat.id,
                f,
                caption=f"📊 Комплексный отчет по объекту: {report_data['object_info']['name']}"
            )
        
        # Краткое текстовое резюме
        summary = template_manager.render('comprehensive_report', 
            object_name=report_data['object_info']['name'],
            total_cost=report_data['financial_analysis']['total_cost'],
            materials_cost=report_data['financial_analysis']['materials_cost'],
            salaries_cost=report_data['financial_analysis']['salaries_cost']
        )
        
        bot.send_message(call.message.chat.id, summary)
        bot.answer_callback_query(call.id, "Отчет сгенерирован")
        
    except Exception as e:
        logger.error(f"Report generation error: {e}")
        bot.send_message(call.message.chat.id, "❌ Ошибка генерации отчета")
        bot.answer_callback_query(call.id, "Ошибка генерации")

@bot.message_handler(content_types=['document'])
@safe_execute()
@track_metrics('file_upload')
def handle_documents(message):
    """Обработка загружаемых файлов"""
    try:
        file_info = bot.get_file(message.document.file_id)
        downloaded_file = bot.download_file(file_info.file_path)
        
        # Сохраняем файл
        filepath = file_manager.save_uploaded_file(
            downloaded_file, 
            message.document.file_name,
            message.from_user.id
        )
        
        file_info = file_manager.get_file_info(filepath)
        
        response = f"""
✅ Файл успешно сохранен!

📁 Имя: {file_info['filename']}
📦 Размер: {file_info['size'] / 1024:.1f} KB
📅 Загружен: {file_info['created'].strftime('%d.%m.%Y %H:%M')}

💡 Файл будет доступен в разделе управления файлами.
"""
        bot.reply_to(message, response)
        
    except ValidationError as e:
        bot.reply_to(message, f"❌ {e}")
    except Exception as e:
        logger.error(f"File handling error: {e}")
        bot.reply_to(message, "❌ Ошибка при сохранении файла")

@bot.message_handler(commands=['files'])
@safe_execute()
@track_metrics('files_command')
def files_command(message):
    """Управление файлами"""
    try:
        files = file_manager.list_files(message.from_user.id)
        
        if not files:
            bot.send_message(message.chat.id, "📁 У вас нет сохраненных файлов.")
            return
        
        response = "📁 ВАШИ ФАЙЛЫ:\n\n"
        for i, file in enumerate(files[:10], 1):
            response += f"{i}. {file['filename']}\n"
            response += f"   📦 {file['size'] / 1024:.1f} KB\n"
            response += f"   📅 {file['modified'].strftime('%d.%m.%Y')}\n\n"
        
        if len(files) > 10:
            response += f"... и еще {len(files) - 10} файлов\n"
        
        bot.send_message(message.chat.id, response)
        
    except Exception as e:
        logger.error(f"Files command error: {e}")
        bot.send_message(message.chat.id, "❌ Ошибка при получении списка файлов")

# =============================================================================
# ОБНОВЛЕННОЕ ГЛАВНОЕ МЕНЮ
# =============================================================================

@safe_execute()
def main_menu(chat_id: int, user_name: str = "друг"):
    """Улучшенное главное меню"""
    welcome_message = template_manager.render('welcome', user_name=user_name)
    
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    buttons = [
        types.KeyboardButton('🏗️ Объекты'),
        types.KeyboardButton('📦 Материалы'), 
        types.KeyboardButton('💵 Зарплаты'),
        types.KeyboardButton('📊 Статистика'),
        types.KeyboardButton('🤖 AI Анализ'),
        types.KeyboardButton('🔍 Поиск'),
        types.KeyboardButton('📈 Отчеты'),
        types.KeyboardButton('📁 Файлы'),
        types.KeyboardButton('⚙️ Настройки'),
        types.KeyboardButton('🆘 Помощь')
    ]
    markup.add(*buttons)
    bot.send_message(chat_id, welcome_message, reply_markup=markup)

@bot.message_handler(commands=['start'])
@safe_execute()
@track_metrics('start_command')
def start_command(message):
    """Обработка команды /start с улучшенным приветствием"""
    user_name = message.from_user.first_name or "друг"
    main_menu(message.chat.id, user_name)

@bot.message_handler(func=lambda message: message.text == '🤖 AI Анализ')
@safe_execute()
@track_metrics('ai_analysis_menu')
def ai_analysis_handler(message):
    """Обработка меню AI анализа"""
    analyze_command(message)

@bot.message_handler(func=lambda message: message.text == '🔍 Поиск')
@safe_execute()
@track_metrics('search_menu')
def search_handler(message):
    """Обработка меню поиска"""
    search_command(message)

@bot.message_handler(func=lambda message: message.text == '📈 Отчеты')
@safe_execute()
@track_metrics('reports_menu')
def reports_handler(message):
    """Обработка меню отчетов"""
    report_command(message)

@bot.message_handler(func=lambda message: message.text == '📁 Файлы')
@safe_execute()
@track_metrics('files_menu')
def files_handler(message):
    """Обработка меню файлов"""
    files_command(message)

# =============================================================================
# ОБНОВЛЕННАЯ СИСТЕМА УВЕДОМЛЕНИЙ
# =============================================================================

class EnhancedNotificationManager:
    """Расширенный менеджер уведомлений с интеграцией новых систем"""
    
    def __init__(self, bot_instance, db: DatabaseManager):
        self.bot = bot_instance
        self.db = db
    
    def send_daily_report(self, chat_id: int = None):
        """Расширенный ежедневный отчет с аналитикой"""
        try:
            today = datetime.datetime.now().strftime(EnhancedConfig.DEFAULT_DATE_FORMAT)
            
            # Статистика за сегодня
            daily_stats = self.db.execute_query('''
                SELECT 
                    COUNT(DISTINCT m.object_id) as objects_with_materials,
                    COUNT(DISTINCT s.object_id) as objects_with_salaries,
                    COALESCE(SUM(m.total_cost), 0) as materials_cost,
                    COALESCE(SUM(s.total_salary), 0) as salaries_cost,
                    COUNT(DISTINCT s.worker_name) as workers_count
                FROM 
                    (SELECT 1) as dummy
                    LEFT JOIN materials m ON m.date = ?
                    LEFT JOIN salaries s ON s.date = ?
            ''', (today, today))[0]
            
            # Общая статистика
            total_objects = self.db.execute_query('SELECT COUNT(*) FROM objects WHERE status = "active"')[0][0]
            total_expenses_result = self.db.execute_query('''
                SELECT COALESCE(SUM(total_cost), 0) + COALESCE(SUM(total_salary), 0)
                FROM (
                    SELECT total_cost FROM materials
                    UNION ALL
                    SELECT total_salary FROM salaries
                )
            ''')[0][0] or 0
            
            # Статистика за текущий месяц
            current_month = datetime.datetime.now().strftime('%Y-%m')
            monthly_stats = self.db.execute_query('''
                SELECT 
                    COALESCE(SUM(m.total_cost), 0),
                    COALESCE(SUM(s.total_salary), 0)
                FROM 
                    (SELECT 1) as dummy
                    LEFT JOIN materials m ON strftime('%Y-%m', m.date) = ?
                    LEFT JOIN salaries s ON strftime('%Y-%m', s.date) = ?
            ''', (current_month, current_month))[0]
            
            monthly_total = (monthly_stats[0] or 0) + (monthly_stats[1] or 0)
            
            # Генерируем отчет через шаблон
            report = template_manager.render('daily_report',
                date=datetime.datetime.now().strftime('%d.%m.%Y'),
                objects_with_materials=daily_stats[0] or 0,
                objects_with_salaries=daily_stats[1] or 0,
                workers_count=daily_stats[4] or 0,
                materials_cost=daily_stats[2] or 0,
                salaries_cost=daily_stats[3] or 0,
                daily_total=(daily_stats[2] or 0) + (daily_stats[3] or 0),
                total_objects=total_objects,
                total_expenses=total_expenses_result,
                monthly_total=monthly_total
            )
            
            if chat_id:
                self.bot.send_message(chat_id, report)
            else:
                self._send_to_admins(report)
            
            logger.info("Enhanced daily report sent")
            
        except Exception as e:
            logger.error(f"Error in enhanced daily report: {e}")
    
    def send_budget_alert(self, object_id: int, current_usage: float, budget: float):
        """Улучшенные уведомления о бюджете с аналитикой"""
        usage_percent = (current_usage / budget) * 100
        
        if usage_percent >= 80:  # Более низкий порог для раннего предупреждения
            object_info = self.db.execute_query(
                'SELECT name FROM objects WHERE id = ?', 
                (object_id,)
            )[0]
            
            # Получаем AI рекомендации
            recommendations = analytics_engine.optimize_costs(object_id)
            
            alert_level = 'critical' if usage_percent >= 90 else 'high' if usage_percent >= 80 else 'medium'
            
            recommendation_text = ""
            if recommendations:
                top_rec = recommendations[0]
                recommendation_text = f"{top_rec.title}: {top_rec.description}"
            
            alert = template_manager.render('budget_alert',
                object_name=object_info[0],
                current_usage=current_usage,
                budget=budget,
                usage_percent=usage_percent,
                alert_level=alert_level,
                recommendation=recommendation_text
            )
            
            self._send_to_admins(alert)
            
            # Отправляем вебхук
            asyncio.create_task(webhook_manager.send_webhook('budget_alert', {
                'object_id': object_id,
                'object_name': object_info[0],
                'usage_percent': usage_percent,
                'alert_level': alert_level
            }))
    
    def _send_to_admins(self, message: str):
        """Отправка сообщения администраторам"""
        for admin_id in SecurityConfig.ADMIN_IDS:
            try:
                self.bot.send_message(admin_id, message)
            except Exception as e:
                logger.error(f"Error sending message to admin {admin_id}: {e}")

# =============================================================================
# ОБНОВЛЕННЫЙ ЗАПУСК СИСТЕМЫ
# =============================================================================

def enhanced_main():
    """Улучшенная основная функция запуска"""
    logger.info("🚀 Запуск улучшенной версии Construction Manager Bot...")
    
    # Валидация конфигурации
    try:
        EnhancedConfig.validate_config()
        logger.info("✅ Конфигурация проверена")
    except Exception as e:
        logger.error(f"❌ Ошибка валидации конфигурации: {e}")
        return
    
    # Проверяем и обновляем базу данных
    try:
        db._init_tables()
        db._init_indexes()
        logger.info("✅ База данных проверена и готова к работе")
    except Exception as e:
        logger.error(f"❌ Ошибка инициализации БД: {e}")
        return
    
    # Создаем начальный бэкап
    try:
        if os.path.exists(EnhancedConfig.DB_PATH):
            EnhancedBackupManager.create_backup()
            logger.info("✅ Начальный бэкап создан")
    except Exception as e:
        logger.error(f"⚠️ Не удалось создать начальный бэкап: {e}")
    
    # Проверка здоровья системы при запуске
    try:
        health_status = health_checker.check_system_health()
        if health_status['overall_status'] != 'healthy':
            logger.warning(f"⚠️ Система запущена с проблемами: {health_status}")
        else:
            logger.info("✅ Система запущена в здоровом состоянии")
    except Exception as e:
        logger.error(f"⚠️ Ошибка проверки здоровья при запуске: {e}")
    
    # Запускаем фоновые задачи
    background_tasks.start()
    
    # Настройка вебхуков из переменных окружения
    webhook_url = os.getenv('WEBHOOK_URL')
    if webhook_url:
        webhook_manager.add_webhook(webhook_url, os.getenv('WEBHOOK_SECRET'))
        logger.info(f"✅ Вебхук настроен: {webhook_url}")
    
    logger.info("✅ Бот успешно запущен и готов к работе!")
    logger.info("✨ Доступные улучшения:")
    logger.info("   • AI-аналитика и прогнозы")
    logger.info("   • Расширенная система поиска") 
    logger.info("   • Комплексные отчеты")
    logger.info("   • Управление файлами")
    logger.info("   • Мониторинг здоровья системы")
    logger.info("   • Вебхук интеграции")
    logger.info("   • Шаблонизация сообщений")
    
    # Основной цикл бота
    while True:
        try:
            bot.polling(none_stop=True, interval=0, timeout=60)
        except Exception as e:
            logger.error(f"❌ Ошибка в работе бота: {e}")
            logger.info("🔄 Перезапуск через 15 секунд...")
            
            # Отправляем уведомление о перезапуске
            try:
                health_report = health_checker.generate_health_report()
                for admin_id in SecurityConfig.ADMIN_IDS:
                    bot.send_message(admin_id, f"🔄 Бот перезапускается из-за ошибки:\n{str(e)[:500]}")
            except:
                pass
            
            time.sleep(15)

if __name__ == "__main__":
    enhanced_main()
