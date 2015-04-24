import json
import os
import sys
import warnings
from service_host.service import Service
from service_host.exceptions import ServiceError
from optional_django import six
if six.PY2:
    from urllib import pathname2url
else:
    from urllib.request import pathname2url
from optional_django.safestring import mark_safe
from optional_django import staticfiles
from .exceptions import ImproperlyConfigured, ConfigFileNotFound, BundlingError
from .conf import settings

service = Service(settings.SERVICE_NAME)


class WebpackBundle(object):
    stats = None

    def __init__(self, stats):
        self.stats = stats

    def __str__(self):
        return mark_safe(self.render())

    def __unicode__(self):
        return mark_safe(unicode(self.render()))

    def render(self):
        """
        Returns HTML script elements pointing to the bundle's assets
        """
        urls = self.get_urls()
        if urls:
            scripts = ['<script src="{url}"></script>'.format(url=url) for url in urls]
            return mark_safe(''.join(scripts))
        return ''

    def get_assets(self):
        if self.stats:
            assets = []
            paths_to_assets = self.stats.get('pathsToAssets', {})
            urls_to_assets = self.stats.get('urlsToAssets', {})
            for asset in self.stats.get('assets', None):
                name = asset['name']
                assets.append({
                    'name': name,
                    'path': paths_to_assets.get(name, None),
                    'url': urls_to_assets.get(name, None),
                })
            return assets

    def get_paths(self):
        """
        Returns paths to the bundle's assets
        """
        return [asset['paths'] for asset in self.get_assets() if asset['paths']]

    def get_urls(self):
        """
        Returns urls to the bundle's assets
        """
        return [asset['url'] for asset in self.get_assets() if asset['url']]

    def get_config(self):
        if self.stats:
            return self.stats.get('webpackConfig', None)

    def get_library(self):
        config = self.get_config()
        if config and 'output' in config:
            return config['output'].get('library', None)
    get_var = get_library  # Convenience alias


def webpack(config_file, watch_config=None, watch_source=None):
    if not settings.BUNDLE_ROOT:
        raise ImproperlyConfigured(
            'webpack.conf.settings.BUNDLE_ROOT has not been defined. '
            'Please specify a directory to place bundles into'
        )

    if not settings.BUNDLE_URL:
        raise ImproperlyConfigured(
            'webpack.conf.settings.BUNDLE_ROOT has not been defined. '
            'Please specify the url that bundles will be served from'
        )

    if not os.path.isabs(config_file):
        abs_path = staticfiles.find(config_file)
        if not abs_path:
            raise ConfigFileNotFound(config_file)
        config_file = abs_path

    if not os.path.exists(config_file):
        raise ConfigFileNotFound(config_file)

    if watch_config is None:
        watch_config = settings.WATCH_CONFIG_FILES

    if watch_source is None:
        watch_source = settings.WATCH_SOURCE_FILES

    try:
        res = service.call(
            config=config_file,
            watch=watch_source,
            watchDelay=200,
            watchConfig=watch_config,
            cache=False,
            fullStats=settings.OUTPUT_FULL_STATS,
            bundleDir=os.path.join(settings.BUNDLE_ROOT, settings.BUNDLE_DIR),
        )
    except ServiceError as e:
        raise six.reraise(BundlingError, BundlingError(*e.args), sys.exc_info()[2])

    stats = json.loads(res.text)

    if stats['errors']:
        raise BundlingError('\n\n'.join([config_file] + stats['errors']))

    if stats['warnings']:
        warnings.warn(stats['warnings'], Warning)

    stats['urlsToAssets'] = {}

    # Generate contextual information about the generated assets
    path_to_bundle_dir = os.path.join(settings.BUNDLE_ROOT, settings.BUNDLE_DIR)
    for asset, config_file in six.iteritems(stats['pathsToAssets']):
        if path_to_bundle_dir in config_file:
            rel_path = config_file[len(path_to_bundle_dir):]
            rel_url = pathname2url(rel_path)
            if rel_url[0] == '/':
                rel_url = rel_url[1:]
            url = settings.BUNDLE_URL + settings.BUNDLE_DIR + '/' + rel_url
            stats['urlsToAssets'][asset] = url

    return WebpackBundle(stats)