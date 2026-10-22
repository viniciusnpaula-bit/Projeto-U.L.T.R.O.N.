"""Stable identities and input-only discovery for local audio devices."""
import importlib
import json


def _hostapi_name(hostapi):
    """Accept both the PortAudio dict and the attribute object exposed by sounddevice."""
    if isinstance(hostapi, dict):
        return hostapi.get("name")
    return getattr(hostapi, "name", None)


def enumerate_input_devices(audio=None):
    audio = audio or importlib.import_module("sounddevice")
    hostapis = audio.query_hostapis()
    occurrences = {}
    inputs = []
    for index, device in enumerate(audio.query_devices()):
        if int(device.get("max_input_channels", 0)) < 1:
            continue
        hostapi_index = int(device["hostapi"])
        hostapi = str(_hostapi_name(hostapis[hostapi_index]) or hostapi_index)[:128]
        name = str(device.get("name") or "Entrada de áudio")[:256]
        key = (hostapi, name)
        occurrence = occurrences.get(key, 0)
        occurrences[key] = occurrence + 1
        device_id = json.dumps([hostapi, name, occurrence], ensure_ascii=False, separators=(",", ":"))
        inputs.append({"id": device_id, "name": name, "hostapi": hostapi, "index": index})
    return audio, inputs


def resolve_input_device(device_id, audio=None):
    if not isinstance(device_id, str) or len(device_id) > 512:
        return None
    _audio, devices = enumerate_input_devices(audio)
    match = next((device for device in devices if device["id"] == device_id), None)
    return match["index"] if match else None
