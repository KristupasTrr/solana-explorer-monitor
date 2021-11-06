from threading import Thread
import requests
from time import sleep

from requests.exceptions import SSLError
from metaplex import metadata
from datetime import datetime
import json

from metaplex.metadata import *
from solana.rpc.api import Client

from utils import getSettings

API_URL = "https://explorer-api.mainnet-beta.solana.com/"


class NotificationObject():
    def __init__(self, http_client, address, txn_sig):
        self.http_client = http_client
        self.address = address
        self.success = True
        self.txn_signature = txn_sig
        self.txn_url = ""
        self.mint = None
        self.mint_price = None

    def get_transaction_transfer_objects(self, response):
        try:
            if response["result"]["transaction"]["message"]["instructions"][0]["parsed"]["type"] == "transfer":
                return response["result"]["transaction"]["message"]["instructions"][0]["parsed"]["info"]["destination"]
        except:
            return None
        return None

    def get_transaction_change(self, response, address_id):
        try:
            change = response["result"]["meta"]["postBalances"][address_id] - \
                response["result"]["meta"]["preBalances"][address_id]
            return change / 1000000000
        except:
            return None

    def get_account_idx(self, response, address_id):
        for idx, instruction in enumerate(response["result"]["transaction"]["message"]["accountKeys"]):
            if instruction["pubkey"] == address_id:
                return idx
            idx += 1
        return None

    def get_mint_token(self, response):
        for instruction in response["result"]["transaction"]["message"]["instructions"]:
            if instruction["parsed"]["type"] == "mintTo":
                return instruction["parsed"]["info"]["mint"]
        return None

    def get_nft_info(self):
        resp = get_metadata(self.http_client, self.mint)
        metadata_resp = requests.get(url=resp["data"]["uri"]).json()

        self.nft_name = metadata_resp["name"]
        self.nft_desc = metadata_resp["description"]
        self.nft_img_url = metadata_resp["image"]

    def get_txn_info(self):
        resp = self.http_client.get_confirmed_transaction(self.txn_signature, encoding="jsonParsed")

        # get mint price
        address_idx = self.get_account_idx(resp, self.address["id"])
        self.mint_price = self.get_transaction_change(resp, address_idx)

        if self.success:
            # txn type is: MINT TO
            self.mint = self.get_mint_token(resp)
            if self.mint is not None:
                self.txn_url = "https://explorer.solana.com/address/{}".format(self.mint)
                self.get_nft_info()
                return
            # txn type is: TRANSFER
            self.transfer_to = self.get_transaction_transfer_objects(resp)
            if self.transfer_to is not None:
                self.txn_url = "https://explorer.solana.com/tx/{}".format(self.txn_signature)
                return

    def send_hook(self, webhook):

        obj = {
            "embeds": [{
                "username": "Solana Explorer Monitor",
                "avatar_url": "https://s2.coinmarketcap.com/static/img/coins/64x64/5426.png",
                "url": self.txn_url,
                "footer": {
                    "text": "kx tools",
                    "icon_url": "https://s2.coinmarketcap.com/static/img/coins/64x64/5426.png"
                },
                "timestamp": datetime.now().isoformat(),
                "color": 3553598,
                "fields": []
            }]
        }

        obj["embeds"][0]["title"] = "NEW TRANSACTION"
        obj["embeds"][0]["fields"].append({"name": "Mint Price", "value": str("%f" % self.mint_price), "inline": True})

        if not self.success:
            # obj["embeds"][0]["fields"].append({"name": "Price", "value": str("%f" % self.mint_price), "inline": True})
            obj["embeds"][0]["fields"].append({"name": "Result of txn", "value": "FAILED", "inline": True})

        if hasattr(self, "nft_name"):
            obj["embeds"][0]["image"] = { 'url': self.nft_img_url }
            obj["embeds"][0]["title"] = self.nft_name
            obj["embeds"][0]["fields"].append({"name": "Address Minted", "value": self.address["name"], "inline": True})
            obj["embeds"][0]["fields"].append({"name": "Result of txn", "value": "SUCCESS", "inline": True})
            obj["embeds"][0]["fields"].append({"name": "Type of txn", "value": "MINT", "inline": True})
            # obj["embeds"][0]["fields"].append({"name": "Mint Price", "value": str("%f" % self.mint_price), "inline": True})

        if hasattr(self, "transfer_to"):
            if self.transfer_to:
                obj["embeds"][0]["fields"].append({"name": "Source address", "value": self.address["name"], "inline": True})
                obj["embeds"][0]["fields"].append({"name": "Result of txn", "value": "SUCCESS", "inline": True})
                obj["embeds"][0]["fields"].append({"name": "Destination address", "value": self.transfer_to, "inline": True})
                obj["embeds"][0]["fields"].append({"name": "Type of txn", "value": "TRANSFER", "inline": True})

        resp = requests.post(webhook, json=obj)
        while not resp.status_code == 204:
            print("too many requests... retrying...")
            resp = requests.post(webhook, json=obj)
        if resp.status_code == 204:
            return 0


class Monitor(Thread):
    def __init__(self, address, delay, webhook):
        super().__init__()
        self.http_client = Client(API_URL)
        self.address = address
        self.delay = delay
        self.webhook = webhook
        self.daemon = True

    def get_transactions(self):
        resp = self.http_client.get_signatures_for_address(self.address["id"])
        return resp["result"]

    def run(self):
        print("{} | thread is running".format(self.address["name"]))

        # TODO: ADD EXCEPTIONS/RETRIES FOR FAILURES
        curr_txn = self.get_transactions()

        # curr_txn[4] = None
        # curr_txn[10] = None

        while True:
            print("{} | getting new transactions...".format(datetime.now()))
            new_txn = self.get_transactions()

            for key in new_txn:
                if key not in curr_txn:
                    notify = NotificationObject(self.http_client, self.address, key["signature"])
                    print("NEW TXN")

                    if key["err"] is not None:
                        notify.txn_url = "https://explorer.solana.com/tx/{}".format(key["signature"])
                        notify.success = False

                    notify.get_txn_info()

                    notify.send_hook(self.webhook)

            curr_txn = new_txn

            sleep(self.delay)


if __name__ == '__main__':

    settings = getSettings()

    for address in settings["addresses"]:
        Monitor(address, settings["delay"], settings["webhook"]).start()

    while True:
        sleep(100000)
