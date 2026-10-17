from gunicorn.glogging import Logger as GunicornLogger

workers = 4
bind = "0.0.0.0:5000"
accesslog = "-"


class HealthzFilterLogger(GunicornLogger):
    """Drop /healthz access-log lines — the kiosk boot loop polls it every 2s."""

    def access(self, resp, req, environ, request_time):
        if environ.get("PATH_INFO") == "/healthz":
            return
        super().access(resp, req, environ, request_time)


logger_class = HealthzFilterLogger


def post_worker_init(worker):
    # Every worker tries to start the scheduler; a Postgres advisory lock in
    # start_scheduler lets exactly one win. This survives worker respawns,
    # unlike gating on worker.age.
    #
    # post_worker_init (not post_fork) because it runs *after* the worker has
    # loaded the WSGI app, so worker.app.callable is the built Flask app. The
    # scheduler thread must start inside a worker: threads are not inherited
    # across os.fork(), so starting it in the arbiter would run no jobs.
    from app import start_scheduler

    start_scheduler(worker.app.callable)
