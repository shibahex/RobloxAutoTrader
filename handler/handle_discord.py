from discord_webhook import DiscordWebhook, DiscordEmbed
import requests
import time
# Define status colors for better readability and maintainability
STATUS_COLORS = {
    0: "fa0a02",  # Error/Failure (Outbound cancel)
    1: "027efa",  # Info (Send)
    2: "02fa02",  # Success (Accepted)
    3: "fad402"   # Warning (Counter)
}

PLACEHOLDER_IMAGE = "https://i.imgur.com/cS4VYkJ.png"


class DiscordHandler():
    def __init__(self):
        pass

    # NOTE: trade advertisement channel in rolimons is slowmode of 10 mins use a link like https://www.roblox.com/users/97483119/trade and say how much robux u have

    def post_message(self):

        pass

    def scan_channel(self):
        pass

    def scan_value_requests(self):
        pass

    def scan_value_albums(self):
        pass

    def post_webhook(self):
        pass

    def format_trades_api(self, response):
        """
            Makes webhooks for trades.roblox.com/v1/trades
        """

    def trade_profit(self, trade) -> int:
        """
        Calculates the profits for a trade for the webhook info
        """
        # NOTE: the problem is that the bot adds rap + value
        their_rap = trade['their_rap']
        their_value = trade['their_value']
        their_algo = trade['their_rap_algo']
        their_overall = trade['their_overall_value']

        self_robux = trade['self_robux']
        self_rap = trade['self_rap']
        self_value = trade['self_value']
        self_algo = trade['self_rap_algo']
        self_overall = trade['self_overall_value']

        # use to add algo to this but doesnt make sense because its like the RAP
        total_profit = their_overall - self_overall

        algo_profit = round(their_algo - self_algo)
        rap_profit = their_rap - self_rap
        value_profit = their_value - self_value

        return total_profit, algo_profit, rap_profit, value_profit

    def embed_fields_from_trade(self, generated_trade: dict, rolimon_data: dict, projected_data) -> dict:
        # TODO: fix the bug where if theres multiple of the same item it only puts one of them in the webhook
        """
            Takes all the item ids from generated trade and formats their names in a string that have linebreaks
        """
        def str_from_item_ids(item_ids, is_self=False):
            string = ""
            total_sum = 0
            for item in item_ids:
                item_name = rolimon_data[str(item)]['item_name']
                item_total_value = rolimon_data[str(item)]['total_value']
                if str(item) in projected_data:
                    item_algo_value = round(projected_data[str(item)]['value'])
                else:
                    item_algo_value = 0

                string += item_name + \
                    f" ({item_total_value}) Algorithm: ({
                        item_algo_value})" + "\n"
                total_sum += item_total_value
            if is_self and generated_trade['self_robux'] != 0:
                string += f"Robux: {generated_trade['self_robux']}\n"

            string += f"Total: {total_sum}"

            return string

        their_item_ids = generated_trade['their_side_item_ids']
        self_item_ids = generated_trade['self_side_item_ids']

        send_string = str_from_item_ids(self_item_ids, is_self=True)

        receive_string = str_from_item_ids(their_item_ids)

        total_profit, algorithm_profit, rap_profit, value_profit = self.trade_profit(
            generated_trade)

        embed_fields = {
            "Send": (send_string, True),
            "Receive": (receive_string, True),
            "Trade Breakdown": (f"Algorithm Profit: {algorithm_profit} | Rap Profit: {rap_profit} | Value Profit: {value_profit}", False)
        }

        # return total profit for the embed title
        return embed_fields, total_profit

    # , author_icon):
    def setup_embed(self, title: str, color, user_id, embed_fields: dict, footer: str, description=""):
        """
        Creates a Discord Embed with dynamic fields.

        :param user_id: The Roblox user ID for fetching the avatar thumbnail.
        :param embed_fields: A dictionary of embed fields where the key is the field name, 
                             and the value is a tuple (field_value, inline).
        """

        embed = DiscordEmbed(
            title=title, description=description, color=STATUS_COLORS[color])
        embed.set_footer(text=footer+f' • {user_id}')
        embed.set_timestamp()

        try:
            thumbnail = requests.get(f"https://thumbnails.roblox.com/v1/users/avatar-headshot?userIds={
                                     user_id}&size=48x48&format=Png&isCircular=false").json()['data'][0]['imageUrl']
        except:
            thumbnail = PLACEHOLDER_IMAGE
        embed.set_author(name='Doggo Trader', icon_url=thumbnail)
        # embed.set_thumbnail(url=thumbnail)

        for field_name, (field_value, inline) in embed_fields.items():
            embed.add_embed_field(
                name=field_name, value=field_value, inline=inline)

        return embed

    def send_webhook(self, embed: DiscordEmbed, webhook_url: str):
        """
        Sends a webhook to Discord with a detailed message and embed.
        """
        try:
            if webhook_url == "":
                return None
            # Create a webhook instance and setup embed
            webhook = DiscordWebhook(
                url=webhook_url, username="Doggo Tradebot")

            webhook.add_embed(embed)

            # Wait if ratelimited
            while True:
                response = webhook.execute()
                if "429" in str(response):
                    print("Webhook ratelimited waiting 15 secs")
                    time.sleep(15)
                    continue

                time.sleep(0.5)
                break

            print("[DOGGO]", response)
        except Exception as e:
            # Log any errors to help with debugging
            print(f"[ERROR] Failed to send webhook: {e}")
