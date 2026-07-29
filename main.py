from rpaflow.browser import Browser

from src.core.config import Config
from src.portal_fidc import PortalFidc
from src.portal_floorplan import PortalFloorplan


def main():
    config = Config()

    # Browser único com duas páginas
    browser = Browser()
    browser.start(config.floorplan_site)
    browser.maximize()
    
    floorplan = PortalFloorplan(config, browser)
    floorplan.executar()
    pass


if __name__ == "__main__":
    main()

    