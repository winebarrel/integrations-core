# (C) Datadog, Inc. 2018
# All rights reserved
# Licensed under a 3-clause BSD style license (see LICENSE)

from .mixins import PrometheusScraper

from .. import AgentCheck
from ...errors import CheckException

class Scraper(PrometheusScraper):
    def __init__(self, check):
        super(Scraper, self).__init__()
        self.check = check

    def _submit_rate(self, metric_name, val, metric, custom_tags=None, hostname=None):
        """
        Submit a metric as a rate, additional tags provided will be added to
        the ones from the label provided via the metrics object.

        `custom_tags` is an array of 'tag:value' that will be added to the
        metric when sending the rate to Datadog.
        """
        _tags = self._metric_tags(metric_name, val, metric, custom_tags, hostname)
        self.check.rate('{}.{}'.format(self.NAMESPACE, metric_name), val, _tags, hostname=hostname)


    def _submit_gauge(self, metric_name, val, metric, custom_tags=None, hostname=None):
        """
        Submit a metric as a gauge, additional tags provided will be added to
        the ones from the label provided via the metrics object.

        `custom_tags` is an array of 'tag:value' that will be added to the
        metric when sending the gauge to Datadog.
        """
        _tags = self._metric_tags(metric_name, val, metric, custom_tags, hostname)
        self.check.gauge('{}.{}'.format(self.NAMESPACE, metric_name), val, _tags, hostname=hostname)

    def _metric_tags(self, metric_name, val, metric, custom_tags=None, hostname=None):
        _tags = []
        if custom_tags is not None:
            _tags += custom_tags
        for label in metric.label:
            if self.exclude_labels is None or label.name not in self.exclude_labels:
                tag_name = label.name
                if self.labels_mapper is not None and label.name in self.labels_mapper:
                    tag_name = self.labels_mapper[label.name]
                _tags.append('{}:{}'.format(tag_name, label.value))
        return self._finalize_tags_to_submit(_tags, metric_name, val, metric, custom_tags=custom_tags, hostname=hostname)

    def _submit_service_check(self, *args, **kwargs):
        self.check.service_check(*args, **kwargs)


class GenericPrometheusCheck(AgentCheck):
    """
    GenericPrometheusCheck is a class that helps instanciating PrometheusCheck only
    with YAML configurations. As each check has it own states it maintains a map
    of all checks so that the one corresponding to the instance is executed

    Minimal example configuration:
    instances:
    - prometheus_url: http://foobar/endpoint
        namespace: "foobar"
        metrics:
        - bar
        - foo
    """
    def __init__(self, name, init_config, agentConfig, instances=None, default_instances={}, default_namespace=""):
        super(GenericPrometheusCheck, self).__init__(name, init_config, agentConfig, instances)
        self.scrapers_map = {}
        self.default_instances = default_instances
        self.default_namespace = default_namespace
        for instance in instances:
            self.get_scraper(instance)

    def check(self, instance):
        endpoint = instance["prometheus_url"]
        scraper = self.get_scraper(instance)
        if not scraper.metrics_mapper:
            raise CheckException("You have to collect at least one metric from the endpoint: " + endpoint)

        scraper.process(
            endpoint,
            send_histograms_buckets=instance.get('send_histograms_buckets', True),
            instance=instance,
            ignore_unmapped=True
        )

    def _extract_rate_metrics(self, type_overrides):
        rate_metrics = []
        for metric in type_overrides:
            if type_overrides[metric] == "rate":
                rate_metrics.append(metric)
                type_overrides[metric] = "gauge"
        return rate_metrics


    def get_scraper(self, instance):
        namespace = instance.get("namespace", "")
        # Check if we have a namespace
        if namespace == "":
            if self.default_namespace == "":
                raise CheckException("You have to define a namespace for each prometheus check")
            namespace = self.default_namespace

        # Retrieve potential default instance settings for the namespace
        default_instance = self.default_instances.get(namespace, {})
        endpoint = instance.get("prometheus_url", default_instance.get("prometheus_url", ""))
        if endpoint == "":
            raise CheckException("Unable to find prometheus URL in config file.")

        # If we already created the corresponding scraper, return it
        if endpoint in self.scrapers_map:
            return self.scrapers_map[endpoint]

        # Otherwise we create the scraper
        scraper = Scraper(self)
        scraper.NAMESPACE = namespace
        # Metrics are preprocessed if no mapping
        metrics_mapper = {}
        # We merge list and dictionnaries from optional defaults & instance settings
        metrics = default_instance.get("metrics", []) + instance.get("metrics", [])
        for metric in metrics:
            if isinstance(metric, basestring):
                metrics_mapper[metric] = metric
            else:
                metrics_mapper.update(metric)

        scraper.metrics_mapper = metrics_mapper
        scraper.labels_mapper = default_instance.get("labels_mapper", {})
        scraper.labels_mapper.update(instance.get("labels_mapper", {}))
        scraper.label_joins = default_instance.get("label_joins", {})
        scraper.label_joins.update(instance.get("label_joins", {}))
        scraper.rate_metrics = self._extract_rate_metrics(default_instance.get("type_overrides", {}))
        scraper.rate_metrics.extend(self._extract_rate_metrics(instance.get("type_overrides", {})))
        scraper.type_overrides = default_instance.get("type_overrides", {})
        scraper.type_overrides.update(instance.get("type_overrides", {}))
        scraper.exclude_labels = default_instance.get("exclude_labels", []) + instance.get("exclude_labels", [])
        scraper.extra_headers = default_instance.get("extra_headers", {})
        scraper.extra_headers.update(instance.get("extra_headers", {}))
        # For simple values instance settings overrides optional defaults
        scraper.prometheus_metrics_prefix = instance.get("prometheus_metrics_prefix", default_instance.get("prometheus_metrics_prefix", ''))
        scraper.label_to_hostname = instance.get("label_to_hostname", default_instance.get("prometheus_url", ""))
        scraper.health_service_check = instance.get("health_service_check", default_instance.get("health_service_check", True))
        scraper.ssl_cert = instance.get("ssl_cert", default_instance.get("ssl_cert", None))
        scraper.ssl_private_key = instance.get("ssl_private_key", default_instance.get("ssl_private_key", None))
        scraper.ssl_ca_cert = instance.get("ssl_ca_cert", default_instance.get("ssl_ca_cert", None))

        self.scrapers_map[endpoint] = scraper

        return scraper
