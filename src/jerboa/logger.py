import logging

NULL_LOGGER = logging.getLogger("jerboa_null")
NULL_LOGGER.handlers = [logging.NullHandler()]
NULL_LOGGER.propagate = False

formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")

handler = logging.StreamHandler()
handler.setFormatter(formatter)

logger = logging.getLogger("jerboa")
logger.addHandler(handler)
logger.setLevel(logging.INFO)
