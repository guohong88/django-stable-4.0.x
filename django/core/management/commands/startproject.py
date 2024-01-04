from django.core.checks.security.base import SECRET_KEY_INSECURE_PREFIX
from django.core.management.templates import TemplateCommand

from ..utils import get_random_secret_key


class Command(TemplateCommand):
    help = (
        "Creates a Django project directory structure for the given project "
        "name in the current directory or optionally in the given directory."
    )
    missing_args_message = "You must provide a project name."

    def handle(self, **options):
        project_name = options.pop("name")
        target = options.pop("directory")   # {'verbosity': 1, 'settings': None, 'pythonpath': None, 'traceback': False, 'no_color': False, 'force_color': False, 'directory': None, 'template': None, 'extensions': ['py'], 'files': []}

        # Create a random SECRET_KEY to put it in the main settings.
        options["secret_key"] = SECRET_KEY_INSECURE_PREFIX + get_random_secret_key()

        super().handle("project", project_name, target, **options)      # 第一个参数区分创建app还是project
