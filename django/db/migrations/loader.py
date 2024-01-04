import pkgutil
import sys
from importlib import import_module, reload

from django.apps import apps
from django.conf import settings
from django.db.migrations.graph import MigrationGraph
from django.db.migrations.recorder import MigrationRecorder

from .exceptions import (
    AmbiguityError,
    BadMigrationError,
    InconsistentMigrationHistory,
    NodeNotFoundError,
)

MIGRATIONS_MODULE_NAME = "migrations"


class MigrationLoader:
    """ # 通过MigrationLoader对象，可以加载app中的migrations目录下的所有迁移文件
    Load migration files from disk and their status from the database.

    Migration files are expected to live in the "migrations" directory of
    an app. Their names are entirely unimportant from a code perspective,
    but will probably follow the 1234_name.py convention.

    On initialization, this class will scan those directories, and open and
    read the Python files, looking for a class called Migration, which should
    inherit from django.db.migrations.Migration. See
    django.db.migrations.migration for what that looks like.

    Some migrations will be marked as "replacing" another set of migrations.
    These are loaded into a separate set of migrations away from the main ones.
    If all the migrations they replace are either unapplied or missing from
    disk, then they are injected into the main set, replacing the named migrations.
    Any dependency pointers to the replaced migrations are re-pointed to the
    new migration.

    This does mean that this class MUST also talk to the database as well as
    to disk, but this is probably fine. We're already not just operating
    in memory.
    """

    def __init__(
        self,
        connection,
        load=True,  # 是否加载迁移图 默认开启
        ignore_no_migrations=False,
        replace_migrations=True,
    ):
        self.connection = connection    # 传入数据库连接对象
        self.disk_migrations = None     # 磁盘迁移文件
        self.applied_migrations = None  # 完成的迁移文件
        self.ignore_no_migrations = ignore_no_migrations
        self.replace_migrations = replace_migrations
        if load:
            self.build_graph()  # 构建迁移图

    @classmethod
    def migrations_module(cls, app_label):
        """ # 翻译  settings.MIGRATION_MODULE 导入模块(本地setting文件不存在就 导入global_setting文件)
        Return the path to the migrations module for the specified app_label
        and a boolean indicating if the module is specified in
        settings.MIGRATION_MODULE.
        """
        if app_label in settings.MIGRATION_MODULES:
            return settings.MIGRATION_MODULES[app_label], True
        else:
            app_package_name = apps.get_app_config(app_label).name
            return "%s.%s" % (app_package_name, MIGRATIONS_MODULE_NAME), False

    def load_disk(self):
        """Load the migrations from all INSTALLED_APPS from disk."""
        self.disk_migrations = {}       #
        self.unmigrated_apps = set()    # 未迁移的app
        self.migrated_apps = set()      # 已经迁移的app
        for app_config in apps.get_app_configs():
            # Get the migrations module directory 导入格式 ("drf.migrations",False)
            module_name, explicit = self.migrations_module(app_config.label)
            if module_name is None:
                self.unmigrated_apps.add(app_config.label)
                continue
            was_loaded = module_name in sys.modules     # 判断模块是否导入过
            try:
                module = import_module(module_name)    # 导入模块importlib.import_module
            except ModuleNotFoundError as e:           # 模块不存在处理
                if (explicit and self.ignore_no_migrations) or (
                    not explicit and MIGRATIONS_MODULE_NAME in e.name.split(".")
                ):
                    self.unmigrated_apps.add(app_config.label)
                    continue
                raise   # 如果不是上述情况，抛出异常
            else:
                # Module is not a package (e.g. migrations.py).
                if not hasattr(module, "__path__"):     # 判断是否path属性
                    self.unmigrated_apps.add(app_config.label)
                    continue
                # Empty directories are namespaces. Namespace packages have no
                #  翻译  __file__ and don't use a list for __path__. See
                #  https://docs.python.org/3/reference/import.html#namespace-packages
                if getattr(module, "__file__", None) is None and not isinstance(
                    module.__path__, list
                ):
                    self.unmigrated_apps.add(app_config.label)
                    continue
                # 强制重新导入Force a reload if it's already loaded (tests need this)
                if was_loaded:  # 如果模块已经导入过，重新导入
                    reload(module)
            self.migrated_apps.add(app_config.label)  #
            # 应用迁移模块下的所有文件
            migration_names = {   # eg:django.contrib.auth.migrations
                name    # iter_modules 遍历模块下的所有文件(如: 0001_inital.py)
                for _, name, is_pkg in pkgutil.iter_modules(module.__path__)
                if not is_pkg and name[0] not in "_~"
            }
            # Load migrations(
            for migration_name in migration_names:  # ["0001_inital.py"]
                migration_path = "%s.%s" % (module_name, migration_name)
                try:
                    migration_module = import_module(migration_path)  # 导入0001_inital.py文件
                except ImportError as e:
                    if "bad magic number" in str(e):
                        raise ImportError(
                            "Couldn't import %r as it appears to be a stale "
                            ".pyc file." % migration_path
                        ) from e
                    else:
                        raise
                if not hasattr(migration_module, "Migration"):   # 判断是否有Migration类
                    raise BadMigrationError(
                        "Migration %s in app %s has no Migration class"
                        % (migration_name, app_config.label)
                    )
                self.disk_migrations[
                    app_config.label, migration_name   # key("drf","0001_inital.py")
                ] = migration_module.Migration(
                    migration_name,
                    app_config.label,
                )   # 实例化类 Migration

    def get_migration(self, app_label, name_prefix):
        """Return the named migration or raise NodeNotFoundError."""
        return self.graph.nodes[app_label, name_prefix]

    def get_migration_by_prefix(self, app_label, name_prefix):
        """
        Return the migration(s) which match the given app label and name_prefix.
        """
        # Do the search
        results = []
        for migration_app_label, migration_name in self.disk_migrations:
            if migration_app_label == app_label and migration_name.startswith(
                name_prefix
            ):
                results.append((migration_app_label, migration_name))
        if len(results) > 1:
            raise AmbiguityError(
                "There is more than one migration for '%s' with the prefix '%s'"
                % (app_label, name_prefix)
            )
        elif not results:
            raise KeyError(
                f"There is no migration for '{app_label}' with the prefix "
                f"'{name_prefix}'"
            )
        else:
            return self.disk_migrations[results[0]]

    def check_key(self, key, current_app):
        if (key[1] != "__first__" and key[1] != "__latest__") or key in self.graph:
            return key
        # Special-case __first__, which means "the first migration" for
        # migrated apps, and is ignored for unmigrated apps. It allows
        # makemigrations to declare dependencies on apps before they even have
        # migrations.
        if key[0] == current_app:
            # Ignore __first__ references to the same app (#22325)
            return
        if key[0] in self.unmigrated_apps:
            # This app isn't migrated, but something depends on it.
            # The models will get auto-added into the state, though
            # so we're fine.
            return
        if key[0] in self.migrated_apps:
            try:
                if key[1] == "__first__":
                    return self.graph.root_nodes(key[0])[0]
                else:  # "__latest__"
                    return self.graph.leaf_nodes(key[0])[0]
            except IndexError:
                if self.ignore_no_migrations:
                    return None
                else:
                    raise ValueError(
                        "Dependency on app with no migrations: %s" % key[0]
                    )
        raise ValueError("Dependency on unknown app: %s" % key[0])

    def add_internal_dependencies(self, key, migration):
        """ 不是frist 就会依赖于上一个迁移文件(__first_根节点)
        Internal dependencies need to be added first to ensure `__first__`
        dependencies find the correct root node.
        """
        for parent in migration.dependencies:
            # Ignore __first__ references to the same app.
            if parent[0] == key[0] and parent[1] != "__first__":
                self.graph.add_dependency(migration, key, parent, skip_validation=True)

    def add_external_dependencies(self, key, migration):
        for parent in migration.dependencies:
            # Skip internal dependencies 跳过内部依赖
            if key[0] == parent[0]:
                continue
            parent = self.check_key(parent, key[0])
            if parent is not None:
                self.graph.add_dependency(migration, key, parent, skip_validation=True)
        for child in migration.run_before:
            child = self.check_key(child, key[0])   #  rub_before的迁移节点都是他子节点
            if child is not None:
                self.graph.add_dependency(migration, child, key, skip_validation=True)

    def build_graph(self):
        """
        Build a migration dependency graph using both the disk and database.
        You'll need to rebuild the graph if you apply migrations. This isn't
        usually a problem as generally migration stuff runs in a one-shot process.
        """
        # Load disk data  #翻译 加载磁盘数据
        self.load_disk()
        # Load database data
        if self.connection is None:
            self.applied_migrations = {}
        else:
            recorder = MigrationRecorder(self.connection)
            self.applied_migrations = recorder.applied_migrations()
        # To start, populate the migration graph with nodes for ALL migrations
        # and their dependencies. Also make note of replacing migrations at this step.
        self.graph = MigrationGraph()
        self.replacements = {}
        for key, migration in self.disk_migrations.items():
            self.graph.add_node(key, migration)     # 添加所有节点
            # Replacing migrations.
            if migration.replaces:      # 替换节点
                self.replacements[key] = migration
        for key, migration in self.disk_migrations.items():
            # Internal (same app) dependencies.
            self.add_internal_dependencies(key, migration)  # 添加内部依赖
        # Add external dependencies now that the internal ones have been resolved.
        for key, migration in self.disk_migrations.items():
            self.add_external_dependencies(key, migration)  # 添加外部依赖
        # 执行替换 Carry out replacements where possible and if enabled.
        if self.replace_migrations:
            for key, migration in self.replacements.items():
                # Get applied status of each of this migration's replacement
                # targets.
                applied_statuses = [
                    (target in self.applied_migrations) for target in migration.replaces
                ]
                # The replacing migration is only marked as applied if all of
                # its replacement targets are.
                if all(applied_statuses):
                    self.applied_migrations[key] = migration
                else:
                    self.applied_migrations.pop(key, None)
                # A replacing migration can be used if either all or none of
                # its replacement targets have been applied.
                if all(applied_statuses) or (not any(applied_statuses)):
                    self.graph.remove_replaced_nodes(key, migration.replaces)
                else:
                    # This replacing migration cannot be used because it is
                    # partially applied. Remove it from the graph and remap
                    # dependencies to it (#25945).
                    self.graph.remove_replacement_node(key, migration.replaces)
        # Ensure the graph is consistent. # 翻译 确保图形一致(移除无效节点)
        try:
            self.graph.validate_consistency()
        except NodeNotFoundError as exc:
            # Check if the missing node could have been replaced by any squash
            # migration but wasn't because the squash migration was partially
            # applied before. In that case raise a more understandable exception
            # (#23556).
            # Get reverse replacements.
            reverse_replacements = {}
            for key, migration in self.replacements.items():
                for replaced in migration.replaces:
                    reverse_replacements.setdefault(replaced, set()).add(key)
            # Try to reraise exception with more detail.
            if exc.node in reverse_replacements:
                candidates = reverse_replacements.get(exc.node, set())
                is_replaced = any(
                    candidate in self.graph.nodes for candidate in candidates
                )
                if not is_replaced:
                    tries = ", ".join("%s.%s" % c for c in candidates)
                    raise NodeNotFoundError(
                        "Migration {0} depends on nonexistent node ('{1}', '{2}'). "
                        "Django tried to replace migration {1}.{2} with any of [{3}] "
                        "but wasn't able to because some of the replaced migrations "
                        "are already applied.".format(
                            exc.origin, exc.node[0], exc.node[1], tries
                        ),
                        exc.node,
                    ) from exc
            raise
        self.graph.ensure_not_cyclic()  # 循环检测

    def check_consistent_history(self, connection):
        """ # 迁移记录做检查 --如果有任何应用的迁移具有未应用的依赖项，则引发InconsistentMigrationHistory。
        Raise InconsistentMigrationHistory if any applied migrations have unapplied dependencies.
        """
        recorder = MigrationRecorder(connection)
        applied = recorder.applied_migrations()    # todo 迁移记录
        for migration in applied:   # 遍历迁移记录
            # If the migration is unknown, skip it. 如果迁移未知，则跳过它。迁移文件没有数据库有
            if migration not in self.graph.nodes:
                continue
            for parent in self.graph.node_map[migration].parents:
                if parent not in applied:
                    # Skip unapplied squashed migrations that have all of their
                    # `replaces` applied.
                    if parent in self.replacements:
                        if all(
                            m in applied for m in self.replacements[parent].replaces
                        ):
                            continue
                    # parent not in self.replacements # parent 不在替换列表里面
                    raise InconsistentMigrationHistory(
                        "Migration {}.{} is applied before its dependency "
                        "{}.{} on database '{}'.".format(
                            migration[0],
                            migration[1],
                            parent[0],
                            parent[1],
                            connection.alias,
                        )
                    )

    def detect_conflicts(self):
        """ app最后迁移存在多个叶子节点
        # 翻译
        Look through the loaded graph and detect any conflicts - apps
        with more than one leaf migration. Return a dict of the app labels
        that conflict with the migration names that conflict.
        """
        seen_apps = {}
        conflicting_apps = set()
        for app_label, migration_name in self.graph.leaf_nodes():
            if app_label in seen_apps:
                conflicting_apps.add(app_label)
            seen_apps.setdefault(app_label, set()).add(migration_name)
        return {
            app_label: sorted(seen_apps[app_label]) for app_label in conflicting_apps
        }

    def project_state(self, nodes=None, at_end=True):
        """
        Return a ProjectState object representing the most recent state
        that the loaded migrations represent.

        See graph.make_state() for the meaning of "nodes" and "at_end".
        """
        return self.graph.make_state(
            nodes=nodes, at_end=at_end, real_apps=self.unmigrated_apps
        )

    def collect_sql(self, plan):
        """
        Take a migration plan and return a list of collected SQL statements
        that represent the best-efforts version of that plan.
        """
        statements = []
        state = None
        for migration, backwards in plan:
            with self.connection.schema_editor(
                collect_sql=True, atomic=migration.atomic
            ) as schema_editor:
                if state is None:
                    state = self.project_state(
                        (migration.app_label, migration.name), at_end=False
                    )
                if not backwards:
                    state = migration.apply(state, schema_editor, collect_sql=True)
                else:
                    state = migration.unapply(state, schema_editor, collect_sql=True)
            statements.extend(schema_editor.collected_sql)
        return statements
