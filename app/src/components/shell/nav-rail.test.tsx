import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { describe, expect, it } from "vitest";
import { NavRail } from "./nav-rail";

/** The tiles lit while `page` is open. */
function litOn(page: string): string[] {
  render(
    <MemoryRouter initialEntries={[page]}>
      <NavRail />
    </MemoryRouter>,
  );
  return screen
    .getAllByRole("link")
    .filter((tile) => tile.getAttribute("aria-current") === "page")
    .map((tile) => tile.textContent ?? "");
}

describe("NavRail", () => {
  it("lists Mado's places in order", () => {
    render(
      <MemoryRouter>
        <NavRail />
      </MemoryRouter>,
    );

    expect(screen.getAllByRole("link").map((tile) => tile.textContent)).toEqual([
      "Home",
      "Settings",
    ]);
  });

  it.each([
    ["/", "Home"],
    ["/settings", "Settings"],
    ["/settings/about", "Settings"],
  ])("keeps the place of %s lit: %s", (page, tile) => {
    expect(litOn(page)).toEqual([tile]);
  });
});
