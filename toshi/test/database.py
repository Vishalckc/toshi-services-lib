import asyncio
import testing.postgresql
from toshi.database import prepare_database

POSTGRESQL_FACTORY = testing.postgresql.PostgresqlFactory(cache_initialized_db=True, auto_start=False)
    #postgres_args="-h 127.0.0.1 -F -c logging_collector=on -c log_directory=/tmp/log -c log_filename=postgresql-%Y-%m-%d_%H%M%S.log -c log_statement=all")

def requires_database(func=None):
    """Used to ensure all database connections are returned to the pool
    before finishing the test"""
    def wrap(fn):

        async def wrapper(self, *args, **kwargs):

            psql = POSTGRESQL_FACTORY()
            # this fixes a regression in the testing.commons library that causes
            # the setup method to be called multiple times when `cache_initialize_db`
            # is used without an init_handler
            psql.setup()
            psql.start()

            self.pool = self._app.connection_pool = await prepare_database(psql.dsn())

            self._app.config['database'] = psql.dsn()

            try:
                f = fn(self, *args, **kwargs)
                if asyncio.iscoroutine(f):
                    await f

                # wait for all the connections to be released
                if hasattr(self._app.connection_pool, '_con_count'):
                    # pre 0.10.0
                    con_count = lambda: self._app.connection_pool._con_count
                elif hasattr(self._app.connection_pool, '_holders'):
                    # post 0.10.0
                    con_count = lambda: len(self._app.connection_pool._holders)
                else:
                    raise Exception("Don't know how to get connection pool count")
                while con_count() != self._app.connection_pool._queue.qsize():
                    # if there are connections still in use, there should be some
                    # other things awaiting to be run. this simply pass control back
                    # to the ioloop to continue execution, looping until all the
                    # connections are released.
                    future = asyncio.Future()
                    self.io_loop.add_callback(lambda: future.set_result(True))
                    await future
            finally:
                psql.stop()

        return wrapper

    if func is not None:
        return wrap(func)
    else:
        return wrap
