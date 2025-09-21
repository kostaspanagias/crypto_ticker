# /lib/button.py
from machine import Pin, Timer
import time

class Button:
    def __init__(self, pin_id, callback, long_press_callback=None, long_press_ms=2000):
        self.pin = Pin(pin_id, Pin.IN, Pin.PULL_UP)
        self.callback = callback
        self.long_press_callback = long_press_callback
        self.long_press_ms = long_press_ms
        self._debounce_timer = Timer()
        self._long_press_timer = Timer()
        self._is_pressed = False
        self.pin.irq(trigger=Pin.IRQ_FALLING | Pin.IRQ_RISING, handler=self._irq_handler)

    def _debounce_handler(self, t):
        current_value = self.pin.value()
        if current_value == 0 and not self._is_pressed: # Pressed
            self._is_pressed = True
            if self.long_press_callback:
                self._long_press_timer.init(mode=Timer.ONE_SHOT, period=self.long_press_ms, callback=self._long_press_trigger)
        elif current_value == 1 and self._is_pressed: # Released
            self._is_pressed = False
            self._long_press_timer.deinit()
            if self.callback:
                self.callback(self.pin)

    def _long_press_trigger(self, t):
        if self._is_pressed and self.long_press_callback:
            self.long_press_callback(self.pin)
            # Prevent short press callback on release after a long press
            self.callback = None 

    def _irq_handler(self, pin):
        self._debounce_timer.deinit()
        self._debounce_timer.init(mode=Timer.ONE_SHOT, period=50, callback=self._debounce_handler)
