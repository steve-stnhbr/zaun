from abc import ABC, abstractmethod

class TemperatureAPI:

    @abstractmethod
    def set_temperature(self, temperature) -> bool:
        pass

    @abstractmethod
    def get_temperature(self) -> float:
        pass