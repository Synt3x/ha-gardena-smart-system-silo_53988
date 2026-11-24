# Changelog

## 0.5.0 (beta)

**New**
- **Winter mode**: a switch for a mower that's put away. It's no longer shown as
  *Unavailable* or as a problem, even if the gateway is unplugged too.
- The setup wizard can **turn on the gateway's local API** for you.
- Setup accepts a pasted web address, and the whole gateway ID as password.
- Explanations in the setup and settings forms.
- Clear error messages, in English and Swedish, when a command doesn't work.

**Changed**
- Settings: the common choices come first, and fields show their units.
- Two mowers on one gateway get different device names (the end of the serial number).

**Fixed**
- After a power cut, the integration could start without any entities and stay that
  way. It now keeps trying until the gateway reports the mower.
- A new password was refused if the gateway didn't report the mower at that moment.

**For developers**: automated tests, and validation on GitHub.

## 0.4.0

- Continuous position reporting, *Mowing ends*, zones 1–4, version sensors.
- More error texts. Entities that were always empty were removed.

## 0.3.x

- Zones from the app, automatic start, position sensors, *Last contact*, icon.

## 0.1.0

- First beta.
