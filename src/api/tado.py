
from .generic import TemperatureAPI
from libtado import api
from datetime import datetime, date, time
import pytz

# TODO: support multiple zones
# TODO: implement automatic temperature adjustment when schedule changes (when schedule reactivates, set the temperature again)
class TadoTemperatureAPI(TemperatureAPI):
    def __init__(self, email, password, client_secret):
        self.tado_api_client = api.Tado(email, password, client_secret)
        self.default_zone_id = self.tado_api_client.get_zones()[0]['id']
        print("TadoTemperatureAPI: zoneID: %s" % self.default_zone_id)
        print("TadoState", self.tado_api_client.get_state(self.default_zone_id))
        self.temperature = 0
    
    def set_temperature(self, temperature) -> bool:
        result = self.tado_api_client.set_temperature(temperature=temperature, zone=self.default_zone_id, termination='AUTO')
        self.temperature = temperature
        if result is not None:
            return True
        return False

    def get_temperature(self) -> float:
        result = self.tado_api_client.get_zone_states()['zoneStates']
        temp = result[str(self.default_zone_id)]['setting']['temperature']
        return temp['celsius']
    
    def get_current_temperature(self) -> float:
        result = self.tado_api_client.get_state(self.default_zone_id)
        return result['sensorDataPoints']['insideTemperature']['celsius']
    
    def is_in_heating_mode(self) -> bool:
        result = self.tado_api_client.get_schedule_blocks(schedule=1, zone=self.default_zone_id)
        type = 'MONDAY_TO_FRIDAY' if datetime.today().weekday() < 5 else 'SATURDAY' if datetime.today().weekday() == 5 else 'SUNDAY'
        for block in result:
            if block['dayType'] != type:
                continue
            timestr = datetime.now().astimezone(pytz.timezone('CET')).strftime("%H:%M")
            endstr = '23:59' if block['end'] == '00:00' else block['end']
            print(block['start'], timestr, endstr)
            if block['start'] <= timestr <= endstr:
                return block['setting']['power'] == 'ON' and block['setting']['temperature']['celsius'] > self.get_current_temperature()
        return False
