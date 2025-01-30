### Author: Dmitry Fedin <dmitry.fedin@gmail.com>, Ming-Hung Chen <minghung.chen@gmail.com>


class dool_plugin(dool):
    """
    Bytes received or sent through infiniband/RoCE interfaces, using perfquery
    Usage:
        dool --ibpq -N <adapter name>:<port>,total
        default dool --ibpq is the same as
        dool --ibpq -N total

        example for Mellanox adapter, transfering data via port 2
        dool --ibpq -Nmlx4_0:2
    """

    def __init__(self):
        self.nick = ("recv", "send")
        self.type = "d"
        self.cols = 2
        self.width = 6

        self._lids = {}

    @staticmethod
    def _get_devices():
        import re
        from subprocess import check_output

        output = check_output(["ibv_devinfo"]).decode("utf-8")
        devices = []
        current_device = None
        current_port = None

        for line in output.splitlines():
            hca_match = re.match(r"hca_id:\s+(\S+)", line)
            port_match = re.match(r"\s+port:\s*(\d+)", line)
            lid_match = re.match(r"\s+port_lid:\s+(\d+)", line)

            if hca_match:
                current_device = hca_match.group(1)
            elif port_match:
                current_port = int(port_match.group(1))
            elif lid_match:
                if current_device is not None and current_port is not None:
                    lid = int(lid_match.group(1))
                    if lid != 0:
                        devices.append((f"{current_device}:{current_port}", lid))

                current_device = None
                current_port = None

        return devices

    @staticmethod
    def _query_lid_counters(lid):
        import re
        from subprocess import check_output

        output = check_output(["perfquery", "-x", str(lid), "1"]).decode("utf-8")
        rx_data = tx_data = None

        for line in output.splitlines():
            m = re.match(r"^(.+?):\.+(\d+)", line)
            if not m:
                continue

            key, value = m.groups()
            value = int(value)
            match key:
                case "PortXmitData":
                    tx_data = value
                case "PortRcvData":
                    rx_data = value

            if rx_data is not None and tx_data is not None:
                return (rx_data, tx_data)

        raise ValueError("failed to parse")

    def discover(self, *objlist):
        devs = self._get_devices()
        self._lids = dict(devs)

        ret = sorted(name for (name, _) in devs)
        ret += objlist
        return ret

    def vars(self):
        ret = []
        if op.netlist:
            varlist = op.netlist
        elif not op.full:
            varlist = ("total",)
        else:
            varlist = self.discover
            varlist.sort()
        for name in varlist:
            if name in self.discover + ["total"]:
                ret.append(name)
        if not ret:
            raise Exception("No suitable network interfaces found to monitor")
        return ret

    def name(self):
        return ["ib/" + name for name in self.vars]

    def extract(self):
        self.set2["total"] = [0, 0]
        factor = {"total": 1.0}
        ifaces = self.discover
        for name in self.vars:
            self.set2[name] = [0, 0]
        for name in ifaces:
            counters = self._query_lid_counters(self._lids[name])
            factor[name] = 4.0
            if name in self.vars:
                self.set2[name] = counters
            self.set2["total"] = (
                self.set2["total"][0] + counters[0] * factor[name],
                self.set2["total"][1] + counters[1] * factor[name],
            )
        if update:
            for name in self.set2:
                self.val[name] = [
                    (self.set2[name][0] - self.set1[name][0]) * factor[name] / elapsed,
                    (self.set2[name][1] - self.set1[name][1]) * factor[name] / elapsed,
                ]
                if self.val[name][0] < 0:
                    self.val[name][0] += maxint + 1
                if self.val[name][1] < 0:
                    self.val[name][1] += maxint + 1
        if step == op.delay:
            self.set1.update(self.set2)
