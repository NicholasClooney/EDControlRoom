# macOS Virtual Controller Output Research

Date: 2026-05-26

## Goal

Evaluate whether this project should pursue virtual joystick or game-controller output on macOS for Elite Dangerous running through CrossOver.

## Recommendation

Do not make virtual controller output part of the macOS MVP.

For this repo's near-term goals, keyboard injection remains the practical path. A true system-visible virtual controller on modern macOS is possible in principle, but the supported paths are gated behind Apple entitlements, DriverKit/system-extension packaging, and elevated install/runtime complexity. That is a poor fit for the current stage of the project.

If controller output becomes important later, the most realistic macOS path is to prototype a dedicated helper app or sidecar around Apple's `CoreHID` / `HIDVirtualDevice` APIs or a DriverKit-based implementation, not to bolt it directly into the Python autopilot process.

## Findings

### 1. macOS has an official virtual HID path now

Apple documents `CoreHID` and `HIDVirtualDevice` as an official way to emulate HID devices, including virtual devices that send input to other apps.

What this means:
- There is now an Apple-supported API surface for virtual HID devices in user space.
- This is materially better than relying on old kext-era hacks.
- It does not automatically mean a normal local script or unsigned app can create a system-visible virtual gamepad.

### 2. Apple also gates virtual HID behind entitlements

Apple documents:
- `com.apple.developer.hid.virtual.device`
- `com.apple.developer.driverkit.family.hid.virtual.device`

The DriverKit documentation also says virtual HID access requires requesting entitlements from Apple.

Practical implication:
- A plain Python process is not the intended integration point.
- Packaging, signing, entitlements, and likely a helper app/system extension are part of the supported path.

### 3. Existing real-world implementations are heavy

Karabiner's `Karabiner-DriverKit-VirtualHIDDevice` is the best current proof that a modern macOS virtual HID device can work in practice. But its model is heavyweight:
- installed package
- DriverKit driver
- manager app
- daemon
- root-required client communication
- Apple-granted DriverKit entitlements for building/distribution

It is also aimed at virtual keyboard and mouse, not gamepad output.

This is useful as an architectural reference, but not a drop-in answer for a small Python automation project.

### 4. `GameController` virtual controllers are not the right abstraction

Apple's `GCVirtualController` is for adding software controls to your own game/app experience. It is not a general system-wide virtual Xbox/joystick device that another arbitrary app consumes as a hardware controller.

For this project, that means:
- `GCVirtualController` is not the solution
- `CoreHID` / DriverKit is the relevant branch

## Local PoC Attempt

I validated two things locally on this Mac:

1. `CoreHID` is present and importable in Swift.
2. A plain local Swift process could reference `HIDVirtualDevice`, but creating a virtual HID device returned `nil`.

This was done outside repo code as a probe, not as product code.

Interpretation:
- The API exists on this machine.
- A simple local process is not enough to create the device successfully.
- The likely blocker is entitlement/signing/runtime policy, not basic API availability.

This is exactly the kind of result that makes a repo-level MVP PoC unattractive right now.

## Feasibility Assessment

### Near-term macOS feasibility

For a low-friction, redistributable, Python-led MVP: poor.

Main reasons:
- special Apple entitlements
- probable requirement for an app/helper packaging model
- system-extension or driver-style install flow for the robust path
- possible admin/root requirements
- significant support burden compared with keyboard injection, which already works for this repo

### Medium-term macOS feasibility

Possible, but should be treated as a separate subsystem or companion app.

A realistic implementation would likely look like:
- a small signed Swift app/helper
- virtual HID device management in Swift, not Python
- local IPC from Python to the helper
- explicit installation and permission steps

## Required Permissions / System Pieces

Based on Apple's documentation and Karabiner's published implementation, expect some combination of:
- Apple Developer account
- Apple-approved entitlements for virtual HID / DriverKit
- code signing
- notarization for distribution
- app packaging rather than loose scripts
- system extension / driver activation for the DriverKit route
- possible root privileges for the client/daemon model

This is much heavier than Accessibility-style keyboard injection.

## Windows / Linux Shape Later

### Windows

Windows has strong virtual HID/gamepad support, but the common routes are also driver-shaped.

Relevant options:
- Microsoft's Virtual HID Framework (VHF) for a HID source driver
- third-party ecosystems like ViGEm-style virtual gamepad drivers

Implication:
- the clean, robust path is also not "just Python"
- expect a helper binary/driver layer
- if future parity matters, design the autopilot around an abstract output interface now

### Linux

Linux is the cleanest platform for this problem.

The kernel `uinput` interface allows user-space processes to create virtual input devices, including joystick-like devices, by writing to `/dev/uinput`.

Implication:
- Linux is the most script-friendly platform for virtual controller output
- permissions are still relevant, but the architectural path is much simpler than macOS

## What This Means For This Project

For this project, the practical decision is:
- keep macOS MVP on keyboard-based control
- keep platform adapters clean so controller output could become an optional backend later
- do not stall the current port on virtual joystick ambitions

## Future Value For Background Autopiloting

Virtual controller output may still be worth future investment if the project later needs more background-friendly or less focus-sensitive control semantics than keyboard injection can provide.

Potential reasons to revisit it later:
- more natural axis-style steering than discrete keyboard events
- cleaner separation between user keyboard activity and autopilot output
- a path that may reduce reliance on focused-window keyboard delivery

But that should only happen after the current macOS keyboard-based port proves its limits in practice.

Practical conclusion:
- not worth blocking the MVP for
- worth preserving as a future backend option if background control becomes a real requirement

## If We Decide To Pursue This Later

Next implementation step:

Build a separate experimental Swift helper outside the main Python runtime that tries to create a virtual HID device through `CoreHID`, then exposes a tiny local IPC API for setting axes/buttons. Treat it as a standalone research track with its own packaging/signing work, not as a quick feature branch inside the current autopilot port.

## Sources

- Apple `CoreHID` overview: https://developer.apple.com/documentation/CoreHID
- Apple `Creating virtual devices`: https://developer.apple.com/documentation/corehid/creatingvirtualdevices
- Apple `HIDVirtualDevice`: https://developer.apple.com/documentation/corehid/hidvirtualdevice
- Apple entitlement `com.apple.developer.hid.virtual.device`: https://developer.apple.com/documentation/bundleresources/entitlements/com.apple.developer.hid.virtual.device
- Apple entitlement `com.apple.developer.driverkit.family.hid.virtual.device`: https://developer.apple.com/documentation/bundleresources/entitlements/com.apple.developer.driverkit.family.hid.virtual.device
- Apple DriverKit overview: https://developer.apple.com/documentation/driverkit
- Apple system extensions overview: https://developer.apple.com/system-extensions/
- Apple `GCVirtualController`: https://developer.apple.com/documentation/GameController/GCVirtualController
- Apple Game Controller framework overview: https://developer.apple.com/documentation/gamecontroller
- Apple `Configuring game controllers`: https://developer.apple.com/documentation/xcode/configuring-game-controllers
- Karabiner DriverKit virtual HID implementation: https://github.com/pqrs-org/Karabiner-DriverKit-VirtualHIDDevice
- Microsoft VHF overview: https://learn.microsoft.com/en-us/windows-hardware/drivers/hid/virtual-hid-framework--vhf-
- Microsoft HID overview: https://learn.microsoft.com/en-us/windows-hardware/drivers/ddi/_hid/
- Linux `uinput` documentation: https://www.kernel.org/doc/html/v4.12/input/uinput.html
