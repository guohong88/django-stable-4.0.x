from django.apps.registry import Apps
from django.db import DatabaseError, models
from django.utils.functional import classproperty
from django.utils.timezone import now

from .exceptions import MigrationSchemaMissing


class MigrationRecorder:
    """ 迁移记录的保存 关联 django_migrations表
    Deal with storing migration records in the database.  翻译：处理在数据库中存储迁移记录。

    Because this table is actually itself used for dealing with model
    creation, it's the one thing we can't do normally via migrations.
    We manually handle table creation/schema updating (using schema backend)
    and then have a floating model to do queries with.

    If a migration is unapplied its row is removed from the table. Having
    a row in the table always means a migration is applied.
    """

    _migration_class = None     # Migration(models.Model):  # 定义内部模型迁移类

    @classproperty
    def Migration(cls):
        """定义返回模型迁移类   _migration_class = Migration
        Lazy load to avoid AppRegistryNotReady if installed apps import
        MigrationRecorder.
        """
        if cls._migration_class is None:
            #   We use the historical model to read migrations from the table 翻译 ：我们使用历史模型从表中读取迁移
            class Migration(models.Model):  # 定义模型迁移类
                app = models.CharField(max_length=255)
                name = models.CharField(max_length=255)
                applied = models.DateTimeField(default=now)

                class Meta:
                    apps = Apps()
                    app_label = "migrations"
                    db_table = "django_migrations"

                def __str__(self):
                    return "Migration %s for %s" % (self.name, self.app)

            cls._migration_class = Migration
        return cls._migration_class

    def __init__(self, connection):
        """迁移记录的保存"""
        self.connection = connection    # 传入数据库连接对象 \django\db\__init__.py

    @property
    def migration_qs(self):
        """" 返回模型迁移类的查询集"""
        return self.Migration.objects.using(self.connection.alias)

    def has_table(self):
        """ # 如果django_migrations表存在，则返回True。Return True if the django_migrations table exists. """
        with self.connection.cursor() as cursor:
            tables = self.connection.introspection.table_names(cursor)  # TODO 返回数据库中的所有表名
        return self.Migration._meta.db_table in tables # "django_migrations"

    def ensure_schema(self):
        """ # # 确保表存不存在创建 Ensure the table exists and has the correct schema. """
        # If the table's there, that's fine - we've never changed its schema  # in the codebase.
        if self.has_table():
            return
        # Make the table
        try:
            with self.connection.schema_editor() as editor:     # TODO 返回数据库编辑器对象
                editor.create_model(self.Migration)
        except DatabaseError as exc:
            raise MigrationSchemaMissing(
                "Unable to create the django_migrations table (%s)" % exc
            )

    def applied_migrations(self):
        """ # 元祖为key 迁移  (migration.app, migration.name): migration。Return a dict mapping (app_name, migration_name) to Migration instances for all applied migrations.          """
        if self.has_table():
            return {
                (migration.app, migration.name): migration for migration in self.migration_qs
            }
        else:
            # If the django_migrations table doesn't exist, then no migrations
            # are applied.
            return {}

    def record_applied(self, app, name):
        """新增迁移记录Record that a migration was applied."""
        self.ensure_schema()
        self.migration_qs.create(app=app, name=name)

    def record_unapplied(self, app, name):
        """删除迁移记录Record that a migration was unapplied."""
        self.ensure_schema()
        self.migration_qs.filter(app=app, name=name).delete()

    def flush(self):
        """删除所有迁移记录 Delete all migration records. Useful for testing migrations."""
        self.migration_qs.all().delete()
