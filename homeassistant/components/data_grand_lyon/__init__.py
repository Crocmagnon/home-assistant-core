"""The Data Grand Lyon integration."""

from data_grand_lyon_ha import DataGrandLyonClient

from homeassistant.const import CONF_PASSWORD, CONF_USERNAME, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import LOGGER, SUBENTRY_TYPE_STOP, SUBENTRY_TYPE_VELOV_STATION
from .coordinator import (
    DataGrandLyonConfigEntry,
    DataGrandLyonRuntimeData,
    TclCoordinator,
    VelovCoordinator,
)

PLATFORMS: list[Platform] = [Platform.SENSOR]


async def async_setup_entry(
    hass: HomeAssistant, entry: DataGrandLyonConfigEntry
) -> bool:
    """Set up Data Grand Lyon from a config entry."""
    session = async_get_clientsession(hass)
    client = DataGrandLyonClient(
        session=session,
        username=entry.data[CONF_USERNAME],
        password=entry.data[CONF_PASSWORD],
    )

    runtime_data = DataGrandLyonRuntimeData()

    if list(entry.get_subentries_of_type(SUBENTRY_TYPE_STOP)):
        tcl = TclCoordinator(hass, entry, client)
        try:
            await tcl.async_config_entry_first_refresh()
            runtime_data.tcl_coordinator = tcl
        except ConfigEntryNotReady:
            LOGGER.warning("TCL coordinator failed first refresh")

    if list(entry.get_subentries_of_type(SUBENTRY_TYPE_VELOV_STATION)):
        velov = VelovCoordinator(hass, entry, client)
        try:
            await velov.async_config_entry_first_refresh()
            runtime_data.velov_coordinator = velov
        except ConfigEntryNotReady:
            LOGGER.warning("Vélo'v coordinator failed first refresh")

    if runtime_data.tcl_coordinator is None and runtime_data.velov_coordinator is None:
        raise ConfigEntryNotReady("All coordinators failed")

    entry.runtime_data = runtime_data

    entry.async_on_unload(entry.add_update_listener(async_update_entry))

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_update_entry(
    hass: HomeAssistant, entry: DataGrandLyonConfigEntry
) -> None:
    """Handle config entry update (e.g., subentry changes)."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(
    hass: HomeAssistant, entry: DataGrandLyonConfigEntry
) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
