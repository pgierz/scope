# -*- coding: utf-8 -*-
"""
Not sure what to do with this stuff yet...
"""


class SimObj(object):

    NAME = "Generic Sim Object"

    def after_run(self):
        print(
            "This hook could be run after a supercompter job is finished for ",
            self.NAME,
        )

    def before_recieve(self):
        print("This hook could be run recieving information into the generic layer!")

    def before_send(self):
        print(
            "This hook could be run before sending information into the generic layer!"
        )

    def send(self):
        raise NotImplementedError("You haven't overriden the send method, sorry!")

    def recieve(self):
        raise NotImplementedError("You haven't overriden the recieve method, sorry!")


class Model(SimObj):

    NAME = "Generic Model Object"

    def __init__(self):
        print("Model set up!")


class Component(SimObj):

    NAME = "Generic Component Object"

    def __init__(self):
        print("Component set up!")
