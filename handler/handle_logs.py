import logging
import os
import time


class Logging():
    """
    A class to handle logging with severity levels,
    It allows for logging messages with different severity levels,
    """

    severityStruct = {
        0: "[Info]",
        1: "[Alert]",
        2: "[Warning]",
        3: "[Error]",
        4: "[Critical]",
        5: "[Debugging]",
    }

    def __init__(self, log_dir="logs"):
        self.log_dir = log_dir

        if not os.path.exists(self.log_dir):
            os.makedirs(self.log_dir)

        current_time = time.strftime("%I-%M-%S-%p-%m-%d-%Y")
        log_file = os.path.join(self.log_dir, f"{current_time}.log")
        logging.basicConfig(filename=log_file, level=logging.INFO)

    def log(self, msg, dontPrint=False, severityNum=0) -> None:
        '''
        Takes a message then prints and logs it

        dontPrint: bool
        severityNum is:
        0 = Info
        1 = Alert
        2 = Warning
        3 = Error
        4 = Critical
        5 = Debugging

        Example:
        log("Hello Word", False, 0)
        '''
        severity = self.severityStruct.get(severityNum)
        if severity is None:
            print("Invalid severity changing to [INVALID]")
            severity = "[INVALID]"

        if dontPrint is not True:
            print(f"{severity} {msg}")
        else:
            print("Dont print for", msg)
        logMessage = f"{time.time()}: {severity} {msg}"

        logging.info(logMessage)

    @staticmethod
    def cleanupLogs(log_dir="logs", maxLogs=5):
        log_files = [f for f in os.listdir(log_dir) if f.endswith(".log")]
        log_files = sorted(log_files, key=lambda x: os.path.getmtime(
            os.path.join(log_dir, x)), reverse=True)
        files_to_delete = log_files[maxLogs::]
        for file in files_to_delete:
            file_path = os.path.join(log_dir, file)
            os.remove(file_path)
            print(f"Deleted old log file: {file_path}")


# Instantiate the logger globally
logger = Logging()
log = logger.log
logger.cleanupLogs()
