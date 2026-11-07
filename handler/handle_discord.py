from discord_webhook import DiscordWebhook, DiscordEmbed
import requests
import time
from handler.handle_logs import log
from handler.exceptions_types import UnknownItem

# Define status colors for better readability and maintainability
STATUS_COLORS = {
    0: "fa0a02",  # Error/Failure (Outbound cancel)
    1: "027efa",  # Info (Send)
    2: "02fa02",  # Success (Accepted)
    3: "fad402",  # Warning (Counter)
}

PLACEHOLDER_IMAGE = "https://i.imgur.com/cS4VYkJ.png"


class DiscordHandler:
    def __init__(self):
        pass

    def trade_profit(self, trade) -> int:
        """
        Calculates the profits for a trade for the webhook info
        """
        their_rap = trade["their_rap"]
        their_value = trade["their_value"]
        their_algo = trade["their_rap_algo"]
        their_overall = trade["their_overall_value"]

        self_rap = trade["self_rap"]
        self_value = trade["self_value"]
        self_algo = trade["self_rap_algo"]
        self_overall = trade["self_overall_value"]

        # Robux counts toward everything but Value, like when the trade was checked
        robux = (trade.get("their_robux") or 0) - (trade.get("self_robux") or 0)
        total_profit = their_overall - self_overall + robux

        algo_profit = round(their_algo - self_algo + robux)
        rap_profit = their_rap - self_rap + robux
        value_profit = their_value - self_value

        return total_profit, algo_profit, rap_profit, value_profit

    def embed_fields_from_trade(
        self, generated_trade: dict, rolimon_data: dict, projected_data
    ) -> dict:
        """
        Takes all the item ids from generated trade and formats their names in a string that have linebreaks.
        Item id lists keep duplicates, so two of the same item are listed twice.
        """

        def str_from_item_ids(item_ids, is_self=False):
            string = ""
            total_sum = 0
            for item in item_ids:
                item_data = rolimon_data.get(str(item))
                if item_data is None:
                    raise UnknownItem(item)
                item_name = item_data["item_name"]
                item_total_value = item_data["total_value"] or 0
                projected = (projected_data or {}).get(str(item)) or {}
                item_algo_value = round(projected.get("value") or 0)

                string += (
                    item_name
                    + f" ({item_total_value}) Algorithm: ({item_algo_value})"
                    + "\n"
                )
                total_sum += item_total_value
            if is_self and generated_trade["self_robux"] != 0:
                string += f"Robux: {generated_trade['self_robux']}\n"

            string += f"Total: {total_sum}"

            return string

        their_item_ids = generated_trade["their_side_item_ids"]
        self_item_ids = generated_trade["self_side_item_ids"]

        send_string = str_from_item_ids(self_item_ids, is_self=True)

        receive_string = str_from_item_ids(their_item_ids)

        total_profit, algorithm_profit, rap_profit, value_profit = self.trade_profit(
            generated_trade
        )

        embed_fields = {
            "Send": (send_string, True),
            "Receive": (receive_string, True),
            "Trade Breakdown": (
                f"Algorithm Profit: {algorithm_profit} | Rap Profit: {rap_profit} | Value Profit: {value_profit}",
                False,
            ),
        }

        # return total profit for the embed title
        return embed_fields, total_profit

    # , author_icon):
    def setup_embed(
        self,
        title: str,
        color,
        user_id,
        embed_fields: dict,
        footer: str,
        description="",
    ):
        """
        Creates a Discord Embed with dynamic fields.

        :param user_id: The Roblox user ID for fetching the avatar thumbnail.
        :param embed_fields: A dictionary of embed fields where the key is the field name,
                             and the value is a tuple (field_value, inline).
        """

        embed = DiscordEmbed(
            title=title, description=description, color=STATUS_COLORS[color]
        )
        embed.set_footer(text=" • ".join(str(part) for part in (footer, user_id) if part))
        embed.set_timestamp()

        try:
            thumbnail = requests.get(
                f"https://thumbnails.roblox.com/v1/users/avatar-headshot?userIds={
                    user_id
                }&size=48x48&format=Png&isCircular=false",
                timeout=10,
            ).json()["data"][0]["imageUrl"]
        except (requests.RequestException, ValueError, KeyError, IndexError, TypeError):
            thumbnail = PLACEHOLDER_IMAGE
        thumbnail = thumbnail or PLACEHOLDER_IMAGE
        embed.set_author(name="Doggo Trader", icon_url=thumbnail)
        # embed.set_thumbnail(url=thumbnail)

        for field_name, (field_value, inline) in embed_fields.items():
            embed.add_embed_field(name=field_name, value=field_value, inline=inline)

        return embed

    def send_webhook(self, embed: DiscordEmbed, webhook_url: str) -> bool:
        """
        Sends a webhook to Discord with a detailed message and embed.
        Never raises: a failed webhook shouldn't stop trading. Returns True if sent.
        """
        if not webhook_url:
            return False
        try:
            webhook = DiscordWebhook(url=webhook_url, username="Doggo Tradebot")
            webhook.add_embed(embed)

            # Wait if ratelimited, but not forever
            for _ in range(5):
                response = webhook.execute()
                if getattr(response, "status_code", None) == 429 or "429" in str(
                    response
                ):
                    log("[WEBHOOK] Rate limited, waiting 15 seconds", dontPrint=True)
                    time.sleep(15)
                    continue
                time.sleep(0.5)
                log(f"[DOGGO] {response}", dontPrint=True)
                return True

            log("[WEBHOOK] Gave up after repeated rate limits", severityNum=2)
            return False
        except (requests.RequestException, ValueError, TypeError) as e:
            log(f"[WEBHOOK] Couldn't send: {e}", severityNum=2)
            return False

    def send_error(self, webhook_url: str, title: str, details: str) -> bool:
        """Posts an error alert to the optional Error Webhook. Never raises."""
        if not webhook_url:
            return False
        embed = DiscordEmbed(
            title=title[:256], description=details[:4000], color=STATUS_COLORS[0]
        )
        embed.set_timestamp()
        return self.send_webhook(embed, webhook_url)
