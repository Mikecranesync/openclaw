"""Direct Modbus TCP connector — read-only by design."""

from __future__ import annotations

from openclaw.connectors.base import ServiceConnector


class PLCConnector(ServiceConnector):
    """Read-only PLC connector. No write methods — safety by design."""

    def __init__(self, host: str = "", port: int = 502) -> None:
        self._host = host
        self._port = port
        self._client = None

    async def connect(self) -> None:
        if not self._host:
            return
        try:
            from pymodbus.client import AsyncModbusTcpClient
            self._client = AsyncModbusTcpClient(self._host, port=self._port)
            await self._client.connect()
        except ImportError:
            pass  # pymodbus optional

    async def disconnect(self) -> None:
        if self._client:
            try:
                await self._client.close()
            except Exception:
                pass
            self._client = None

    async def read_tags(self) -> dict:
        if not self._client:
            return {}
        coils = await self._client.read_coils(0, 16)
        regs = await self._client.read_holding_registers(0, 10)
        if coils.isError() or regs.isError():
            return {"error": "Read failed"}
        return {
            "motor_running": coils.bits[0],
            "conveyor_running": coils.bits[1],
            "fault_alarm": coils.bits[10],
            "e_stop": coils.bits[11],
            "sensor_1": coils.bits[8],
            "sensor_2": coils.bits[9],
            "motor_speed": regs.registers[0],
            "motor_current": regs.registers[1] / 100.0,
            "temperature": regs.registers[2],
            "pressure": regs.registers[3],
            "conveyor_speed": regs.registers[4],
            "error_code": regs.registers[5],
        }

    async def health_check(self) -> dict:
        if not self._host:
            return {"status": "disabled"}
        if not self._client or not self._client.connected:
            return {"status": "disconnected", "host": self._host}
        return {"status": "connected", "host": self._host, "port": self._port}

    def name(self) -> str:
        return "plc"
