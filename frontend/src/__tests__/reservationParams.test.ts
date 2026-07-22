import { describe, expect, it } from "vitest";

import {
  buildReservationQuery,
  DEFAULT_RESERVATION_FILTERS,
  parseReservationFilters,
  serializeReservationFilters,
} from "../reservation/reservationParams";

describe("reservationParams", () => {
  it("serialize and parse filters round-trip", () => {
    const query = serializeReservationFilters({
      search: "camp",
      statuts: ["soumise", "validee"],
      categories: [3, 7],
      dateRange: ["2026-06-01", "2026-06-02"],
    });

    expect(query).toContain("q=camp");
    expect(query).toContain("statut=soumise%2Cvalidee");
    expect(query).toContain("cat=3%2C7");

    const parsed = parseReservationFilters(`?${query}`);

    expect(parsed).toEqual({
      search: "camp",
      statuts: ["soumise", "validee"],
      categories: [3, 7],
      dateRange: ["2026-06-01", "2026-06-02"],
    });
  });

  it("build query includes only meaningful filters", () => {
    expect(buildReservationQuery(DEFAULT_RESERVATION_FILTERS)).toEqual({});

    expect(
      buildReservationQuery({
        search: "abc",
        statuts: ["brouillon"],
        categories: [4],
        dateRange: ["2026-01-01", null],
      }),
    ).toEqual({
      search: "abc",
      statut: ["brouillon"],
      categories: "4",
      date_from: "2026-01-01",
    });
  });

  it("parse tolerates invalid values", () => {
    const parsed = parseReservationFilters(
      "?cat=2,abc,2&statut=&from=&to=2026-08-01",
    );

    expect(parsed.categories).toEqual([2]);
    expect(parsed.statuts).toEqual([]);
    expect(parsed.dateRange).toEqual([null, "2026-08-01"]);
  });
});
