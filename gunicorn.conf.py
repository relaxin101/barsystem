workers = 4
bind = "0.0.0.0:5000"
accesslog = "-"


def post_worker_init(worker):
    # Start the background scheduler in exactly one worker.
    #
    # We use post_worker_init (not post_fork) because it runs *after* the worker
    # has loaded the WSGI app, so worker.app.callable is the built Flask app
    # (in post_fork it's still None). Starting it inside a live worker means the
    # scheduler's background thread lives in a real, long-lived process. Threads
    # are not inherited across os.fork(), so starting it in the arbiter would
    # leave no worker running the jobs; starting it in create_app() would run it
    # in every worker (jobs firing N times). Gating on worker.age pins it to the
    # first worker the arbiter spawns.
    if worker.age % worker.cfg.workers == 1:
        from app import start_scheduler

        start_scheduler(worker.app.callable)
