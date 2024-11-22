
from .generic import TemperatureAPI
from libtado import api

# TODO: support different zones
# TODO: implement automatic temperature adjustment when schedule changes (when schedule reactivates, set the temperature again)
class TadoTemperatureAPI(TemperatureAPI):
    def __init__(self, email, password, client_secret):
        self.tado_api_client = api.Tado(email, password, client_secret)
        self.default_zone_id = self.tado_api_client.get_zones()[0]['id']
        print("TadoTemperatureAPI: zoneID: %s" % self.default_zone_id)
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