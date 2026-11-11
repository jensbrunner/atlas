from __future__ import annotations

from atlas.ids import slugify
from atlas.state.schemas import InventoryItem
from atlas.tools._util import as_int
from atlas.tools.context import ToolContext, ToolError


def handle_patch_inventory(ctx: ToolContext, args: dict[str, object]) -> str:
    operation = str(args.get("operation", "")).strip().lower()
    name = str(args.get("name", "")).strip()
    if not name:
        raise ToolError("item name is required")
    quantity = as_int(args.get("quantity"), 1)
    if quantity < 0:
        raise ToolError("quantity cannot be negative")
    raw_tags = args.get("tags", [])
    tags = [str(tag) for tag in raw_tags] if isinstance(raw_tags, list) else []

    inventory = ctx.state.character.inventory
    slug = slugify(name)
    item = inventory.get(slug)

    if operation == "add":
        if quantity == 0:
            raise ToolError("cannot add zero items")
        if item is None:
            inventory[slug] = InventoryItem(name=name, quantity=quantity, tags=tags)
        else:
            item.quantity += quantity
            for tag in tags:
                if tag not in item.tags:
                    item.tags.append(tag)
        ctx.note(f"inventory +{quantity} {name}")
        return f"Added {quantity} {name}; now {inventory[slug].quantity}."

    if operation == "remove":
        if item is None:
            raise ToolError(f"character does not carry {name!r}")
        if item.quantity < quantity:
            raise ToolError(f"cannot remove {quantity} {name}; only {item.quantity} carried")
        item.quantity -= quantity
        remaining = item.quantity
        if remaining == 0:
            del inventory[slug]
        ctx.note(f"inventory -{quantity} {name}")
        return f"Removed {quantity} {name}; {remaining} remain."

    if operation == "set":
        if quantity == 0:
            inventory.pop(slug, None)
            ctx.note(f"inventory removed {name}")
            return f"Removed {name}."
        if item is None:
            inventory[slug] = InventoryItem(name=name, quantity=quantity, tags=tags)
        else:
            item.quantity = quantity
        ctx.note(f"inventory set {name}={quantity}")
        return f"Set {name} to {quantity}."

    raise ToolError("operation must be 'add', 'remove', or 'set'")
