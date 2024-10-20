from flask import Flask, request, render_template
import os
import redis
import socket
import logging
from datetime import datetime
from opencensus.ext.azure.log_exporter import AzureLogHandler
from opencensus.ext.azure.trace_exporter import AzureExporter
from opencensus.ext.flask.flask_middleware import FlaskMiddleware
from opencensus.trace.samplers import ProbabilitySampler
from opencensus.trace.tracer import Tracer
from opencensus.ext.azure.metrics_exporter import MetricsExporter
from opencensus.metrics.export.metric_descriptor import MetricDescriptor
from opencensus.metrics.export.time_series import TimeSeries
from opencensus.metrics.export.point import Point
from opencensus.metrics.export.value import ValueDouble
from opencensus.metrics.export.label_key import LabelKey
from opencensus.metrics.export.label_value import LabelValue

# App Insights - Replace 'your-instrumentation-key' with the actual Instrumentation Key
instrumentation_key = '3460234a-f495-4a32-a175-bcc0a300d135'

# Logging setup
logger = logging.getLogger(__name__)
logger.addHandler(AzureLogHandler(connection_string=f'InstrumentationKey={instrumentation_key}'))

# Metrics Exporter
exporter = MetricsExporter(connection_string=f'InstrumentationKey={instrumentation_key}')

# Define Metric Descriptors for Cat and Dog votes
cats_metric_descriptor = MetricDescriptor(
    name="Cats_Vote_Count",
    description="Tracks number of votes for Cats",
    unit="1",
    type_=MetricDescriptor.Type.CUMULATIVE_INT64,
    label_keys=[LabelKey("vote", "vote")]
)

dogs_metric_descriptor = MetricDescriptor(
    name="Dogs_Vote_Count",
    description="Tracks number of votes for Dogs",
    unit="1",
    type_=MetricDescriptor.Type.CUMULATIVE_INT64,
    label_keys=[LabelKey("vote", "vote")]
)

# Tracing setup
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

# Redis Connection
r = redis.Redis()

# Configurations
app.config.from_pyfile('config_file.cfg')
button1 = os.getenv('VOTE1VALUE', app.config['VOTE1VALUE'])
button2 = os.getenv('VOTE2VALUE', app.config['VOTE2VALUE'])
title = os.getenv('TITLE', app.config['TITLE'])

if app.config['SHOWHOST'] == "true":
    title = socket.gethostname()

# Initialize Redis values
if not r.get(button1): r.set(button1, 0)
if not r.get(button2): r.set(button2, 0)

def record_metrics(metric_descriptor, vote_count, vote_label):
    point = Point(ValueDouble(vote_count), datetime.utcnow())
    time_series = TimeSeries(label_values=[LabelValue(vote_label)], points=[point])
    metric = Metric(metric_descriptor=metric_descriptor, time_series=[time_series])
    exporter.export_metrics([metric])

@app.route('/', methods=['GET', 'POST'])
def index():
    vote1 = r.get(button1).decode('utf-8')
    vote2 = r.get(button2).decode('utf-8')

    if request.method == 'GET':
        # Record initial metrics
        record_metrics(cats_metric_descriptor, int(vote1), "Cats")
        record_metrics(dogs_metric_descriptor, int(vote2), "Dogs")

        # Trace votes
        tracer.span(name="cat_vote")
        tracer.span(name="dog_vote")

        return render_template("index.html", value1=int(vote1), value2=int(vote2), button1=button1, button2=button2, title=title)

    elif request.method == 'POST':
        if request.form['vote'] == 'reset':
            r.set(button1, 0)
            r.set(button2, 0)
            vote1 = r.get(button1).decode('utf-8')
            vote2 = r.get(button2).decode('utf-8')

            # Log reset events
            logger.info("Reset Cats Vote", extra={'custom_dimensions': {'Cats Vote': vote1}})
            logger.info("Reset Dogs Vote", extra={'custom_dimensions': {'Dogs Vote': vote2}})

            return render_template("index.html", value1=int(vote1), value2=int(vote2), button1=button1, button2=button2, title=title)
        else:
            vote = request.form['vote']
            r.incr(vote, 1)
            vote1 = r.get(button1).decode('utf-8')
            vote2 = r.get(button2).decode('utf-8')

            # Log vote events
            if vote == button1:
                logger.info("Cats Vote", extra={'custom_dimensions': {'Cats Vote': vote1}})
            else:
                logger.info("Dogs Vote", extra={'custom_dimensions': {'Dogs Vote': vote2}})

            # Trace vote events
            tracer.span(name="cat_vote" if vote == button1 else "dog_vote")

            # Record metrics
            if vote == button1:
                record_metrics(cats_metric_descriptor, int(vote1), "Cats")
            else:
                record_metrics(dogs_metric_descriptor, int(vote2), "Dogs")

            return render_template("index.html", value1=int(vote1), value2=int(vote2), button1=button1, button2=button2, title=title)

if __name__ == "__main__":
    # Run locally
    app.run()
