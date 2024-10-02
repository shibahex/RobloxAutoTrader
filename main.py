import handle_config
def scan_users():
    """
        The process of scanning users should go like:
        1. Get random item from rolimon itemdata
        2. Filter out items according to config like: Minimum Scan owners and minimum value of scanned items
        3. Scan all the owners of the item
        4. Filter out the owners according to config like: Minimum Value, minimum items, last online
    """
    while True:
        pass

if __name__ == "__main__":
    config = handle_config.Config('config.ini')
    print(config.scan_items)
    print(config.filter_users)
