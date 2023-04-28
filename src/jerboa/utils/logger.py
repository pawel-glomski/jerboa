import logging

NULL_LOGGER = logging.getLogger('null')
NULL_LOGGER.handlers = [logging.NullHandler()]
NULL_LOGGER.propagate = False

formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')

handler = logging.StreamHandler()
handler.setFormatter(formatter)

jb_logger = logging.getLogger('jerboa')
jb_logger.addHandler(handler)
jb_logger.setLevel(logging.INFO)
