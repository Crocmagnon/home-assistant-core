"""DataUpdateCoordinator for the Data Grand Lyon integration."""

from dataclasses import dataclass
from datetime import timedelta

from aiohttp import ClientError, ClientResponseError
from data_grand_lyon_ha import (
    DataGrandLyonClient,
    TclPassage,
    VelovStation,
    filter_tcl_passages_by_lines_stops,
    find_velov_stations_by_ids,
)

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    CONF_LINE,
    CONF_STATION_ID,
    CONF_STOP_ID,
    DOMAIN,
    LOGGER,
    SUBENTRY_TYPE_STOP,
    SUBENTRY_TYPE_VELOV_STATION,
)

type DataGrandLyonConfigEntry = ConfigEntry[DataGrandLyonCoordinator]


@dataclass
class DataGrandLyonCoordinatorData:
    """Data returned by the coordinator."""

    stops: dict[str, list[TclPassage]]
    velov_stations: dict[str, VelovStation]


class DataGrandLyonCoordinator(DataUpdateCoordinator[DataGrandLyonCoordinatorData]):
    """Coordinator for the Data Grand Lyon integration."""

    config_entry: DataGrandLyonConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        entry: DataGrandLyonConfigEntry,
        client: DataGrandLyonClient,
    ) -> None:
        """Initialize the coordinator."""
        self.client = client
        super().__init__(
            hass,
            LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=timedelta(minutes=5),
        )

    async def _async_update_data(self) -> DataGrandLyonCoordinatorData:
        """Fetch data for all monitored stops and Vélo'v stations."""
        stop_subentries = list(
            self.config_entry.get_subentries_of_type(SUBENTRY_TYPE_STOP)
        )
        velov_subentries = list(
            self.config_entry.get_subentries_of_type(SUBENTRY_TYPE_VELOV_STATION)
        )

        total = bool(stop_subentries) + bool(velov_subentries)
        success_count = 0

        stops: dict[str, list[TclPassage]] = {}
        velov_stations: dict[str, VelovStation] = {}

        if stop_subentries:
            try:
                all_passages = await self.client.get_tcl_passages()
                lines_stops = [
                    (s.data[CONF_LINE], s.data[CONF_STOP_ID]) for s in stop_subentries
                ]
                filtered = filter_tcl_passages_by_lines_stops(all_passages, lines_stops)
                key_to_subentry = {
                    (s.data[CONF_LINE], s.data[CONF_STOP_ID]): s.subentry_id
                    for s in stop_subentries
                }
                stops = {key_to_subentry[k]: v for k, v in filtered.items()}
                success_count += 1
            except ClientResponseError as err:
                if err.status in (401, 403):
                    raise ConfigEntryAuthFailed(
                        translation_domain=DOMAIN,
                        translation_key="auth_failed",
                    ) from err
                LOGGER.warning("Error fetching TCL passages: %s", err)
            except (ClientError, TimeoutError) as err:
                LOGGER.warning("Error fetching TCL passages: %s", err)

        if velov_subentries:
            try:
                all_stations = await self.client.get_velov_stations()
                station_ids = [s.data[CONF_STATION_ID] for s in velov_subentries]
                found = find_velov_stations_by_ids(all_stations, station_ids)
                id_to_subentry = {
                    s.data[CONF_STATION_ID]: s.subentry_id for s in velov_subentries
                }
                for station_id, station in found.items():
                    if station is not None:
                        velov_stations[id_to_subentry[station_id]] = station
                    else:
                        LOGGER.warning(
                            "Vélo'v station not found for subentry %s",
                            id_to_subentry[station_id],
                        )
                success_count += 1
            except ClientResponseError as err:
                if err.status in (401, 403):
                    raise ConfigEntryAuthFailed(
                        translation_domain=DOMAIN,
                        translation_key="auth_failed",
                    ) from err
                LOGGER.warning("Error fetching Vélo'v stations: %s", err)
            except (ClientError, TimeoutError) as err:
                LOGGER.warning("Error fetching Vélo'v stations: %s", err)

        if total and not success_count:
            raise UpdateFailed(
                translation_domain=DOMAIN,
                translation_key="update_failed_all",
            )
        return DataGrandLyonCoordinatorData(stops=stops, velov_stations=velov_stations)
