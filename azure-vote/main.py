from flask import Flask, request, render_template
import os
import random
import redis
import socket
import sys
import logging
from datetime import datetime
from opencensus.ext.azure.log_exporter import AzureLogHandler
from opencensus.ext.azure.trace_exporter import AzureExporter
from opencensus.ext.flask.flask_middleware import FlaskMiddleware
from opencensus.trace.samplers import ProbabilitySampler
from opencensus.trace.tracer import Tracer
from opencensus.metrics.export import Metrics

# App Insights
# TODO: Replace 'your-instrumentation-key' with the actual Instrumentation Key
instrumentation_key = '3460234a-f495-4a32-a175-bcc0a300d135'

# Logging
logger = logging.getLogger(__name__)
logger.addHandler(AzureLogHandler(connection_string=f'InstrumentationKey={instrumentation_key}'))

# Metrics
metrics = Metrics(exporter=AzureExporter(connection_string=f'InstrumentationKey={instrumentation_key}'))

# Tracing
tracer = Tracer(exporter=AzureExporter(connection_string=f'InstrumentationKey={instrumentation_key}'),
                sampler=ProbabilitySampler(1.0))

# Flask app
app = Flask(__name__)

# Requests middleware
middleware = FlaskMiddleware(
    app,
    exporter=AzureExporter(connection_string=f'InstrumentationKey={instrumentation_key}'),
    sampler=ProbabilitySampler(1.0)
)

# Load configurations from environment or config file
app.config.from_pyfile('config_file.cfg')

if ("VOTE1VALUE" in os.environ and os.environ['VOTE1VALUE']):
    button1 = os.environ['VOTE1VALUE']
else:
    button1 = app.config['VOTE1VALUE']

if ("VOTE2VALUE" in os.environ and os.environ['VOTE2VALUE']):
    button2 = os.environ['VOTE2VALUE']
else:
    button2 = app.config['VOTE2VALUE']

if ("TITLE" in os.environ and os.environ['TITLE']):
    title = os.environ['TITLE']
else:
    title = app.config['TITLE']

# Redis Connection
r = redis.Redis()

# Change title to host name to demo NLB
if app.config['SHOWHOST'] == "true":
    title = socket.gethostname()

# Init Redis
if not r.get(button1): r.set(button1, 0)
if not r.get(button2): r.set(button2, 0)

@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'GET':
        # Get current values
        vote1 = r.get(button1).decode('utf-8')
        vote2 = r.get(button2).decode('utf-8')

        # Trace cat/dog vote
        tracer.span(name="cat_vote")
        tracer.span(name="dog_vote")

        # Return index with values
        return render_template("index.html", value1=int(vote1), value2=int(vote2), button1=button1, button2=button2, title=title)

    elif request.method == 'POST':
        if request.form['vote'] == 'reset':
            # Empty table and return results
            r.set(button1, 0)
            r.set(button2, 0)

            vote1 = r.get(button1).decode('utf-8')
            vote2 = r.get(button2).decode('utf-8')

            # Log reset events
            logger.info("Reset Cats Vote", extra={'custom_dimensions': {'Cats Vote': vote1}})
            logger.info("Reset Dogs Vote", extra={'custom_dimensions': {'Dogs Vote': vote2}})

            return render_template("index.html", value1=int(vote1), value2=int(vote2), button1=button1, button2=button2, title=title)
        else:
            # Insert vote result into DB
            vote = request.form['vote']
            r.incr(vote, 1)

            # Get current values
            vote1 = r.get(button1).decode('utf-8')
            vote2 = r.get(button2).decode('utf-8')

            # Log vote events
            if vote == button1:
                logger.info("Cats Vote", extra={'custom_dimensions': {'Cats Vote': vote1}})
            else:
                logger.info("Dogs Vote", extra={'custom_dimensions': {'Dogs Vote': vote2}})

            # Trace the vote events
            tracer.span(name="cat_vote" if vote == button1 else "dog_vote")

            # Return results
            return render_template("index.html", value1=int(vote1), value2=int(vote2), button1=button1, button2=button2, title=title)

if __name__ == "__main__":
    # Run locally
    app.run()

    # TODO: Use the statement below before deployment to VMSS
    # app.run(host='0.0.0.0', threaded=True, debug=True)  # remote
