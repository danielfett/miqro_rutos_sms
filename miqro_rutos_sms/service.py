"""
MQTT service based on the miqro library.

This service uses the Teltonika RUT SMS API to send SMS messages.

From the Teltonika SMS API documentation:

Action                                  Post/Get URL Examples
View mobile messages list               http://192.168.1.1/cgi-bin/sms_list?username=user1&password=user_pass
Read mobile message                     http://192.168.1.1/cgi-bin/sms_read?username=user1&password=user_pass&number=1
Send mobile message to a single number  http://192.168.1.1/cgi-bin/sms_send?username=user1&password=user_pass&number=0037060000001&text=testmessage
Send mobile message to a group          http://192.168.1.1/cgi-bin/sms_send?username=user1&password=user_pass&group=group_name&text=testmessage
View mobile messages total              http://192.168.1.1/cgi-bin/sms_total?username=user1&password=user_pass
Delete mobile message                   http://192.168.1.1/cgi-bin/sms_delete?username=user1&password=user_pass&number=1

The response to sms_list looks as follows:

Index: 4
Date: Wed Dec 28 17:19:31 2022
Sender: Tarifinfo
Text: Mit der inkludierten Roaming-Option in Ihrem Tarif surfen Sie in der EU ohne Aufpreis wie Zuhause. Aktivieren Sie sorgenfrei Roaming in Ihren Smartphone-EinstelTarifinfo
Status: read
------------------------------
Index: 5
Date: Wed Dec 28 17:18:32 2022
Sender: Tarifinfo
Text:  <part_missing>  <part_missing> res Kontingents befinden, berechnen wir für Nutzung auf vorübergehenden Reisen in der EU (Zone 1) dieselben Preise wie in DeutTarifinfo
Status: read
------------------------------

Configuration required:

host: The IP address or host name of the Teltonika RUT device.
port: The port number of the Teltonika RUT device.
username: The username to use for authentication.
password: The password to use for authentication.
delete_after: If present, delete message after this time. Time is given like a Python timedelta, e.g., "days: 1" 

"""

import requests
from datetime import timedelta, datetime

import miqro


class RUTOSSMSService(miqro.Service):
    SERVICE_NAME = "rutos_sms"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.host = self.service_config.get("host", "192.168.1.1")
        self.port = self.service_config.get("port", 80)
        self.username = self.service_config["username"]
        self.password = self.service_config["password"]
        delete_after = self.service_config.get("delete_after", None)
        if delete_after:
            self.delete_after = timedelta(**delete_after)
        else:
            self.delete_after = None

        self.url = f"http://{self.host}:{self.port}/cgi-bin/"
        self.messages_seen = set()

    @miqro.handle("send/single/#")
    def handle_send_single(self, payload, topic_postfix):
        number = topic_postfix
        text = payload

        self.log.info(f"Sending SMS to {number}: {text}")

        response = requests.get(
            self.url + "sms_send",
            params={
                "username": self.username,
                "password": self.password,
                "number": number,
                "text": text,
            },
        )

        self.log.info(f"Response: {response.text}")
        self.publish(f"sent/single/{number}", response.text)

    @miqro.handle("send/group/#")
    def handle_send_group(self, payload, topic_postfix):
        group = topic_postfix
        text = payload

        self.log.info(f"Sending SMS to group {group}: {text}")

        response = requests.get(
            self.url + "sms_send",
            params={
                "username": self.username,
                "password": self.password,
                "group": group,
                "text": text,
            },
        )

        self.log.info(f"Response: {response.text}")
        self.publish(f"sent/group/{group}", response.text)

    @miqro.handle("delete")
    def handle_delete(self, payload):
        self.delete_message(payload)

    def delete_message(self, index):
        self.log.info(f"Deleting message {index}")

        response = requests.get(
            self.url + "sms_delete",
            params={
                "username": self.username,
                "password": self.password,
                "number": index,
            },
        )

        self.log.info(f"Response: {response.text}")
        self.publish(f"deleted", response.text)

    @miqro.loop(seconds=20)
    def read_and_publish(self):
        """
        Retrieve messages from storage and publish them.
        Messages are published as a JSON object.
        Afterwards, mark messages as read.
        """

        response = requests.get(
            self.url + "sms_list",
            params={
                "username": self.username,
                "password": self.password,
            },
        )

        # log number of lines in response
        self.log.info(f"Response: {len(response.text.splitlines())} lines")

        index = None
        date = None
        sender = None
        text = None
        status = None

        for line in response.text.splitlines():
            if line.startswith("Index: "):
                index = line.split(": ")[1]
            elif line.startswith("Date: "):
                date = line.split(": ", 1)[1]
            elif line.startswith("Sender: "):
                sender = line.split(": ", 1)[1]
            elif line.startswith("Text: "):
                text = line.split(": ", 1)[1]
            elif line.startswith("Status: "):
                status = line.split(": ", 1)[1]
                self.message_arrived(
                    {
                        "index": index,
                        "date": date,
                        "sender": sender,
                        "text": text,
                        "status": status,
                    }
                )
            elif line == "------------------------------":
                index = None
                date = None
                sender = None
                text = None
                status = None

    def message_arrived(self, message):
        # First, check if this message has already been seen.
        # If so, ignore it.

        index = message["index"] + message["date"] + message["sender"]
        if not index in self.messages_seen:
            self.publish("received", message)
            self.messages_seen.add(index)

        # If delete_after is set, delete the message after the given time.
        if self.delete_after:
            date = datetime.strptime(message["date"], "%a %b %d %H:%M:%S %Y")
            if datetime.now() - date > self.delete_after:
                self.delete_message(message["index"])


def run():
    miqro.run(RUTOSSMSService)


if __name__ == "__main__":
    run()
