"""
Based on bza.py (Blazemeter API client) module, and adopted as-is for SignalFX API
"""

import copy
import json
import logging
import os
import sys
import time
import traceback
import uuid
from functools import wraps
from ssl import SSLError

import requests
from requests.exceptions import ReadTimeout

from bzt import TaurusInternalException, TaurusNetworkError, TaurusConfigError
from bzt.engine import Reporter
from bzt.engine import Singletone
from bzt.modules.aggregator import DataPoint, KPISet, ResultsProvider, AggregatorListener
from bzt.six import iteritems, URLError
from bzt.six import string_types
from bzt.six import text_type
from bzt.utils import open_browser
from bzt.utils import to_json, dehumanize_time

NETWORK_PROBLEMS = (IOError, URLError, SSLError, ReadTimeout, TaurusNetworkError)


def send_with_retry(method):
    @wraps(method)
    def _impl(self, *args, **kwargs):
        if not isinstance(self, SignalfxUploader):
            raise TaurusInternalException("send_with_retry should only be applied to SignalfxUploader methods")

        try:
            method(self, *args, **kwargs)
        except (IOError, TaurusNetworkError):
            self.log.debug("Error sending data: %s", traceback.format_exc())
            self.log.warning("Failed to send data, will retry in %s sec...", self._session.timeout)
            try:
                time.sleep(self._session.timeout)
                method(self, *args, **kwargs)
                self.log.info("Succeeded with retry")
            except NETWORK_PROBLEMS:
                self.log.error("Fatal error sending data: %s", traceback.format_exc())
                self.log.warning("Will skip failed data and continue running")

    return _impl


class Session(object):
    def __init__(self):
        super(Session, self).__init__()
        self.address = "https://myrealm.signalfx.com"
        self.data_address = "https://ingest.eu0.signalfx.com/"
        self.dashboard_url = 'https://<REALM>.signalfx.com/#/dashboard/<ID>'
        self.timeout = 30
        self.logger_limit = 256
        self.token = None
        self.token_file = None
        self.log = logging.getLogger(self.__class__.__name__)
        self.http_session = requests.Session()
        self.http_request = self.http_session.request
        self._retry_limit = 5
        self.uuid = None

    def _request(self, url, data=None, headers=None, method=None, raw_result=False, retry=True):
        """
        :param url: str
        :type data: Union[dict,str]
        :param headers: dict
        :param method: str
        :return: dict
        """
        if not headers:
            headers = {}

        has_auth = headers and "X-SF-TOKEN" in headers
        if has_auth:
            pass  # all is good, we have auth provided
        elif isinstance(self.token, string_types):
            token = self.token
            headers["X-SF-TOKEN"] = self.token

        if method:
            log_method = method
        else:
            log_method = 'GET' if data is None else 'POST'

        url = str(url)

        if isinstance(data, text_type):
            data = data.encode("utf-8")

        if isinstance(data, (dict, list)):
            data = to_json(data)
            headers["Content-Type"] = "application/json"

        self.log.debug("Request: %s %s %s", log_method, url, data[:self.logger_limit] if data else None)

        retry_limit = self._retry_limit

        while True:
            try:
                response = self.http_request(
                    method=log_method, url=url, data=data, headers=headers, timeout=self.timeout)
            except requests.ReadTimeout:
                if retry and retry_limit:
                    retry_limit -= 1
                    self.log.warning("ReadTimeout: %s. Retry..." % url)
                    continue
                raise
            break

        resp = response.content
        if not isinstance(resp, str):
            resp = resp.decode()

        self.log.debug("Response [%s]: %s", response.status_code, resp[:self.logger_limit] if resp else None)
        if response.status_code >= 400:
            try:
                result = json.loads(resp) if len(resp) else {}
                if 'error' in result and result['error']:
                    raise TaurusNetworkError("API call error %s: %s" % (url, result['error']))
                else:
                    raise TaurusNetworkError("API call error %s on %s: %s" % (response.status_code, url, result))
            except ValueError:
                raise TaurusNetworkError("API call error %s: %s %s" % (url, response.status_code, response.reason))

        if raw_result:
            return resp

        try:
            result = json.loads(resp) if len(resp) else {}
        except ValueError as exc:
            self.log.debug('Response: %s', resp)
            raise TaurusNetworkError("Non-JSON response from API: %s" % exc)

        if 'error' in result and result['error']:
            raise TaurusNetworkError("API call error %s: %s" % (url, result['error']))

        return result

    def ping(self):
        """ Quick check if we can access the service """
        url = self.address + '/v2/organization'
        self._request(url)

    def send_kpi_data(self, data, is_check_response=True, submit_target=None):
        """
        Sends online data

        :type submit_target: str
        :param is_check_response:
        :type data: str
        """
        # submit_target = self.kpi_target if submit_target is None else submit_target

        url = self.data_address
        response = self._request(url, data)

        if response and 'response_code' in response and response['response_code'] != 200:
            raise TaurusNetworkError("Failed to feed data to %s, response code %s" %
                                     (submit_target, response['response_code']))


class SignalfxUploader(Reporter, AggregatorListener, Singletone):
    """
    Reporter class

    :type _session: bzt.sfa.Session or None
    """

    def __init__(self):
        super(SignalfxUploader, self).__init__()
        self.browser_open = 'start'
        self.project = 'myproject'
        self.custom_tags = {}
        self.additional_tags = {}
        self.kpi_buffer = []
        self.send_interval = 30
        self._last_status_check = time.time()
        self.last_dispatch = 0
        self.results_url = None
        self._test = None
        self._master = None
        self._session = None
        self.first_ts = sys.maxsize
        self.last_ts = 0
        self._dpoint_serializer = DatapointSerializerSFX(self)

    def token_processor(self):
        # Read from config file
        token = self.settings.get("token", "")
        if token:
            self.log.info("Token found in config file")
            return token
        self.log.info("Token not found in config file")
        # Read from environment
        try:
            token = os.environ['SIGNALFX_TOKEN']
            self.log.info("Token found in SIGNALFX_TOKEN environment variable")
            return token
        except:
            self.log.info("Token not found in SIGNALFX_TOKEN environment variable")
            pass
        # Read from file
        try:
            token_file = self.settings.get("token-file","")
            if token_file:
                with open(token_file, 'r') as handle:
                        token = handle.read().strip()
                        self.log.info("Token found in file %s:", token_file)
                        return token
            else:
                self.log.info("Parameter token_file is empty or doesn't exist")
        except:
            self.log.info("Token can't be retrieved from file: %s, please check path or access", token_file)
            
        return None

    def prepare(self):
        """
        Read options for uploading, check that they're sane
        """
        super(SignalfxUploader, self).prepare()
        self.send_interval = dehumanize_time(self.settings.get("send-interval", self.send_interval))
        self.browser_open = self.settings.get("browser-open", self.browser_open)
        self.project = self.settings.get("project", self.project)
        self.custom_tags = self.settings.get("custom-tags", self.custom_tags)
        self._dpoint_serializer.multi = self.settings.get("report-times-multiplier", self._dpoint_serializer.multi)
        token = self.token_processor()
        if not token:
            raise TaurusConfigError("No SignalFX API key provided")

        # direct data feeding case
        
        # Generates uuid withon "-" to avoid conflict in dimensions.
        # Read details here: 
        # https://community.signalfx.com/s/article/Timestamp-and-UUID-data-not-allowable-in-Dimension-values
        
        self.sess_id = str(uuid.uuid4()).replace("-", "") 
          
        self.additional_tags.update({'project': self.project, 'uuid': self.sess_id})
        self.additional_tags.update(self.custom_tags)

        self._session = Session()
        self._session.log = self.log.getChild(self.__class__.__name__)
        self._session.token = token
        self._session.address = self.settings.get("address", self._session.address).rstrip("/")
        self._session.dashboard_url = self.settings.get("dashboard-url", self._session.dashboard_url).rstrip("/")
        self._session.data_address = self.settings.get("data-address", self._session.data_address).rstrip("/")
        self._session.timeout = dehumanize_time(self.settings.get("timeout", self._session.timeout))
        try:
            self._session.ping()  # to check connectivity and auth
        except Exception:
            self.log.error("Cannot reach SignalFX API, maybe the address/token is wrong")
            raise

        if isinstance(self.engine.aggregator, ResultsProvider):
            self.engine.aggregator.add_listener(self)

    def startup(self):
        """
        Initiate online test
        """
        super(SignalfxUploader, self).startup()

        self.results_url = self._session.dashboard_url + \
                           '?startTime=-15m&endTime=Now' + \
                           '&sources%5B%5D=' + \
                           'project:' + \
                           self.project + \
                           '&sources%5B%5D=uuid:' + \
                           self.sess_id + \
                           '&density=4'

        self.log.info("Started data feeding: %s", self.results_url)
        if self.browser_open in ('start', 'both'):
            open_browser(self.results_url)

    def post_process(self):
        """
        Upload results if possible
        """
        self.log.debug("KPI bulk buffer len in post-proc: %s", len(self.kpi_buffer))
        self.log.info("Sending remaining KPI data to server...")
        self.__send_data(self.kpi_buffer, False, True)
        self.kpi_buffer = []

        if self.browser_open in ('end', 'both'):
            open_browser(self.results_url)
        self.log.info("Report link: %s", self.results_url)

    def check(self):
        """
        Send data if any in buffer
        """
        self.log.debug("KPI bulk buffer len: %s", len(self.kpi_buffer))
        if self.last_dispatch < (time.time() - self.send_interval):
            self.last_dispatch = time.time()
            if len(self.kpi_buffer):
                self.__send_data(self.kpi_buffer)
                self.kpi_buffer = []
        return super(SignalfxUploader, self).check()

    @send_with_retry
    def __send_data(self, data, do_check=True, is_final=False):
        """
        :type data: list[bzt.modules.aggregator.DataPoint]
        """

        serialized = self._dpoint_serializer.get_kpi_body(data, self.additional_tags, is_final)
        self._session.send_kpi_data(serialized, do_check)

    def aggregated_second(self, data):
        """
        Send online data
        :param data: DataPoint
        """
        self.kpi_buffer.append(data)


class DatapointSerializerSFX(object):
    def __init__(self, owner):
        """
        :type owner: SignalfxUploader
        """
        super(DatapointSerializerSFX, self).__init__()
        self.owner = owner
        self.multi = 1000  # miltiplier factor for reporting

    def get_kpi_body(self, data_buffer, tags, is_final):
        # - reporting format:
        #   {labels: <data>,    # see below
        #    sourceID: <id of BlazeMeterClient object>,
        #    [is_final: True]}  # for last report
        #
        # - elements of 'data' are described in __get_label()
        #
        # - elements of 'intervals' are described in __get_interval()
        #   every interval contains info about response codes have gotten on it.
        signalfx_labels_list = []

        if data_buffer:
            self.owner.first_ts = min(self.owner.first_ts, data_buffer[0][DataPoint.TIMESTAMP])
            self.owner.last_ts = max(self.owner.last_ts, data_buffer[-1][DataPoint.TIMESTAMP])

            # fill 'Timeline Report' tab with intervals data
            # intervals are received in the additive way
            for dpoint in data_buffer:
                time_stamp = dpoint[DataPoint.TIMESTAMP]
                for label, kpi_set in iteritems(dpoint[DataPoint.CURRENT]):
                    dimensions = copy.deepcopy(tags)
                    dimensions.update({'label': label or 'OVERALL'})
                    label_data = self.__convert_data(kpi_set, time_stamp * self.multi, dimensions)
                    signalfx_labels_list.extend(label_data)

        data = {"gauge": signalfx_labels_list}
        return to_json(data)

    def __convert_data(self, item, timestamp, dimensions):
        # Overall stats : RPS, Threads, procentiles and mix/man/avg
        tmin = int(self.multi * item[KPISet.PERCENTILES]["0.0"]) if "0.0" in item[KPISet.PERCENTILES] else 0
        tmax = int(self.multi * item[KPISet.PERCENTILES]["100.0"]) if "100.0" in item[KPISet.PERCENTILES] else 0
        tavg = self.multi * item[KPISet.AVG_RESP_TIME]
        data = [
            {'timestamp': timestamp, 'metric': 'RPS', 'dimensions': dimensions, 'value': item[KPISet.SAMPLE_COUNT]},
            {'timestamp': timestamp, 'metric': 'Threads', 'dimensions': dimensions, 'value': item[KPISet.CONCURRENCY]},
            {'timestamp': timestamp, 'metric': 'Failures', 'dimensions': dimensions, 'value': item[KPISet.FAILURES]},
            {'timestamp': timestamp, 'metric': 'min', 'dimensions': dimensions, 'value': tmin},
            {'timestamp': timestamp, 'metric': 'max', 'dimensions': dimensions, 'value': tmax},
            {'timestamp': timestamp, 'metric': 'avg', 'dimensions': dimensions, 'value': tavg},
        ]

        for p in item[KPISet.PERCENTILES]:
            tperc = int(self.multi * item[KPISet.PERCENTILES][p])
            data.append({'timestamp': timestamp, 'metric': 'p' + p, 'dimensions': dimensions, 'value': tperc})

        # Detailed info : Error
        for rcode in item[KPISet.RESP_CODES]:
            error_dimensions = copy.deepcopy(dimensions)
            error_dimensions['rc'] = rcode
            rcnt = item[KPISet.RESP_CODES][rcode]
            data.append({'timestamp': timestamp, 'metric': 'rc', 'dimensions': error_dimensions, 'value': rcnt})

        return data
