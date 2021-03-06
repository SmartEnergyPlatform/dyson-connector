"""
   Copyright 2018 InfAI (CC SES)

   Licensed under the Apache License, Version 2.0 (the "License");
   you may not use this file except in compliance with the License.
   You may obtain a copy of the License at

       http://www.apache.org/licenses/LICENSE-2.0

   Unless required by applicable law or agreed to in writing, software
   distributed under the License is distributed on an "AS IS" BASIS,
   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
   See the License for the specific language governing permissions and
   limitations under the License.
"""

try:
    from connector_client.modules.http_lib import Methods as http
    from connector_client.modules.device_pool import DevicePool
    from connector_client.client import Client
    from dyson.configuration import DYSON_CLOUD_API_URL, DYSON_ACCOUNT_EMAIL, DYSON_ACCOUNT_PW, DYSON_ACCOUNT_COUNTRY, DYSON_CLOUD_API_USER, DYSON_CLOUD_API_PW, writeConf
    from dyson.device import DysonDevice, dyson_map
    from dyson.session import SessionManager
    from libpurecoollink.utils import decrypt_password
    from dyson.logger import root_logger
except ImportError as ex:
    exit("{} - {}".format(__name__, ex.msg))
import time, json
from threading import Thread


logger = root_logger.getChild(__name__)


class CloudApiMonitor(Thread):
    def __init__(self):
        super().__init__()
        self._init_sessions = list()
        self._know_devices = list()
        if not (DYSON_CLOUD_API_USER and DYSON_CLOUD_API_PW):
            while not self._getApiCredentials():
                logger.info("retry in 30s")
                time.sleep(30)
        unknown_devices = self._apiQueryDevices()
        self._evaluate(unknown_devices)
        self.start()


    def run(self):
        for session in self._init_sessions:
            session.start()
        while True:
            time.sleep(300)
            unknown_devices = self._apiQueryDevices()
            self._evaluate(unknown_devices)


    def _getApiCredentials(self):
        body = {
            "Email": DYSON_ACCOUNT_EMAIL,
            "Password": DYSON_ACCOUNT_PW
        }
        http_resp = http.post(
            "https://{}/v1/userregistration/authenticate?country={}".format(DYSON_CLOUD_API_URL, DYSON_ACCOUNT_COUNTRY),
            json.dumps(body),
            headers={'Content-Type': 'application/json'},
            verify=False
        )
        if http_resp.status == 200:
            credentials = json.loads(http_resp.body)
            global DYSON_CLOUD_API_USER
            global DYSON_CLOUD_API_PW
            DYSON_CLOUD_API_USER = credentials.get('Account')
            DYSON_CLOUD_API_PW = credentials.get('Password')
            writeConf('DYSON_API', 'user', DYSON_CLOUD_API_USER)
            writeConf('DYSON_API', 'pw', DYSON_CLOUD_API_PW)
            return True
        logger.error("could not retrieve dyson cloud credentials - '{}' - '{}'".format(http_resp.status, http_resp.body))
        return False


    def _apiQueryDevices(self):
        unknown_devices = dict()
        http_resp = http.get(
            "https://api.cp.dyson.com/v1/provisioningservice/manifest",
            auth=(DYSON_CLOUD_API_USER, DYSON_CLOUD_API_PW),
            verify=False
        )
        if http_resp.status == 200:
            devices = json.loads(http_resp.body)
            for device in devices:
                try:
                    unknown_devices[device['Serial']] = device
                except KeyError:
                    logger.error("missing device serial or malformed message - '{}'".format(device))
        return unknown_devices


    def _diff(self, known, unknown):
        known_set = set(known)
        unknown_set = set(unknown)
        missing = known_set - unknown_set
        new = unknown_set - known_set
        return missing, new


    def _evaluate(self, unknown_devices):
        missing_devices, new_devices = self._diff(self._know_devices, unknown_devices)
        if missing_devices:
            for missing_device_id in missing_devices:
                logger.info("can't find '{}'".format(missing_device_id))
                try:
                    Client.delete(missing_device_id)
                except AttributeError:
                    DevicePool.remove(missing_device_id)
                SessionManager.delRemoteDevice(missing_device_id)
        if new_devices:
            for new_device_id in new_devices:
                try:
                    dyson_data = dyson_map[unknown_devices[new_device_id]['ProductType']]
                    dyson_device = DysonDevice(
                        new_device_id,
                        dyson_data['type'],
                        dyson_data['name'],
                        decrypt_password(unknown_devices[new_device_id]['LocalCredentials']),
                        unknown_devices[new_device_id]['ProductType'],
                        unknown_devices[new_device_id]['ScaleUnit']
                    )
                    dyson_device.addTag('manufacturer', 'Dyson')
                    count = ''
                    for tag in dyson_data['tags']:
                        dyson_device.addTag('type{}'.format(count), tag)
                        if not count:
                            count = 0
                        count = count + 1
                    logger.info("found '{}' with id '{}'".format(dyson_device.name, dyson_device.id))
                    SessionManager.addRemoteDevice(dyson_device)
                except KeyError:
                    logger.error("missing device data or malformed message - '{}'".format(unknown_devices[new_device_id]))
        self._know_devices = unknown_devices.keys()
