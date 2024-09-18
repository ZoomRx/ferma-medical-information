import structlog
import ecs_logging
from pathlib import Path
import copy
from sentry_sdk import capture_exception

from helpers.google_pub_sub import publish
from config import settings


def merge_dicts(dict1, dict2):
    for key, value in dict2.items():
        if key in dict1 and isinstance(dict1[key], dict) and isinstance(value, dict):
            merge_dicts(dict1[key], value)
        else:
            dict1[key] = value
    return dict1

def publish_log_to_pubsub(logger, log_method, event_dict):
    try:
        data = event_dict
        if settings.env.environment == "production":
            publish(settings.gcs.gcs_project_id, settings.pubsub.logger_topic, data)
    except Exception as e:
        print(e)
        capture_exception(e)
    return event_dict


class Logger():
    @staticmethod
    def initialise():
        print("Initialise")
        structlog.configure(
            processors=[
                structlog.contextvars.merge_contextvars,
                publish_log_to_pubsub,
                ecs_logging.StructlogFormatter()
            ],
            logger_factory=structlog.WriteLoggerFactory(file=Path("logs/combined").with_suffix(".log").open("at")),
        )

    @staticmethod
    def update_ctx(data: dict = {}):
        context = merge_dicts(structlog.contextvars.get_contextvars(), data)
        structlog.contextvars.bind_contextvars(**context)

    @staticmethod
    def log(level: str = 'info', msg: str = '', data: dict = {}, update_ctx=False):
        prev_context = copy.deepcopy(structlog.contextvars.get_contextvars())
        context = merge_dicts(structlog.contextvars.get_contextvars(), data)
        structlog.contextvars.bind_contextvars(**context)

        for key, value in context.items():
            if isinstance(value, dict):
                for field, details in value.items():
                    if isinstance(details, (dict, list)):
                        context[key][field] = str(details)

            elif isinstance(value, list):
                context[key] = str(value)

        root_logger = structlog.get_logger()
        if level == 'info':
            root_logger.info(msg)
        elif level == 'debug':
            root_logger.debug(msg)
        elif level == 'warning':
            root_logger.warning(msg)
        elif level == 'error':
            root_logger.error(msg)
        elif level == 'critical':
            root_logger.critical(msg)
        else:
            root_logger.info(msg)

        if not update_ctx:
            structlog.contextvars.clear_contextvars()
            structlog.contextvars.bind_contextvars(**prev_context)