import pyrtl


def RefModule(a, b):
    extended_sum = (
        pyrtl.concat(pyrtl.Const(0, bitwidth=1), a)
        + pyrtl.concat(pyrtl.Const(0, bitwidth=1), b)
    )
    s_value = extended_sum[0:8]

    s = pyrtl.WireVector(bitwidth=8, name="s")
    overflow = pyrtl.WireVector(bitwidth=1, name="overflow")

    s <<= s_value
    overflow <<= (a[7] == b[7]) & (a[7] != s_value[7])

    return s, overflow
