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


@dataclass
class DataGrandLyonRuntimeData:
    """Runtime data for the Data Grand Lyon integration."""

    tcl_coordinator: TclCoordinator | None = None
    velov_coordinator: VelovCoordinator | None = None


type DataGrandLyonConfigEntry = ConfigEntry[DataGrandLyonRuntimeData]


class TclCoordinator(DataUpdateCoordinator[dict[str, list[TclPassage]]]):
    """Coordinator for TCL transit data."""

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
            name=f"{DOMAIN}_tcl",
            update_interval=timedelta(minutes=5),
        )

    async def _async_update_data(self) -> dict[str, list[TclPassage]]:
        """Fetch TCL passage data for all monitored stops."""
        stop_subentries = list(
            self.config_entry.get_subentries_of_type(SUBENTRY_TYPE_STOP)
        )

        try:
            all_passages = await self.client.get_tcl_passages()
        except ClientResponseError as err:
            if err.status in (401, 403):
                raise ConfigEntryAuthFailed(
                    translation_domain=DOMAIN,
                    translation_key="auth_failed",
                ) from err
            raise UpdateFailed(f"Error fetching TCL passages: {err}") from err
        except (ClientError, TimeoutError) as err:
            raise UpdateFailed(f"Error fetching TCL passages: {err}") from err

        lines_stops = [
            (s.data[CONF_LINE], s.data[CONF_STOP_ID]) for s in stop_subentries
        ]
        filtered = filter_tcl_passages_by_lines_stops(all_passages, lines_stops)
        key_to_subentry = {
            (s.data[CONF_LINE], s.data[CONF_STOP_ID]): s.subentry_id
            for s in stop_subentries
        }
        return {key_to_subentry[k]: v for k, v in filtered.items()}


class VelovCoordinator(DataUpdateCoordinator[dict[str, VelovStation]]):
    """Coordinator for Vélo'v station data."""

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
            name=f"{DOMAIN}_velov",
            update_interval=timedelta(minutes=5),
        )

    async def _async_update_data(self) -> dict[str, VelovStation]:
        """Fetch Vélo'v station data for all monitored stations."""
        velov_subentries = list(
            self.config_entry.get_subentries_of_type(SUBENTRY_TYPE_VELOV_STATION)
        )

        try:
            all_stations = await self.client.get_velov_stations()
        except ClientResponseError as err:
            if err.status in (401, 403):
                raise ConfigEntryAuthFailed(
                    translation_domain=DOMAIN,
                    translation_key="auth_failed",
                ) from err
            raise UpdateFailed(f"Error fetching Vélo'v stations: {err}") from err
        except (ClientError, TimeoutError) as err:
            raise UpdateFailed(f"Error fetching Vélo'v stations: {err}") from err

        station_ids = [s.data[CONF_STATION_ID] for s in velov_subentries]
        found = find_velov_stations_by_ids(all_stations, station_ids)
        id_to_subentry = {
            s.data[CONF_STATION_ID]: s.subentry_id for s in velov_subentries
        }

        result: dict[str, VelovStation] = {}
        for station_id, station in found.items():
            if station is not None:
                result[id_to_subentry[station_id]] = station
            else:
                LOGGER.warning(
                    "Vélo'v station not found for subentry %s",
                    id_to_subentry[station_id],
                )
        return result
