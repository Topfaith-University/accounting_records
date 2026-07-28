/** Plain-integer date-only arithmetic (no Date/timezone involved) so results
 * don't depend on the machine's local timezone — mirrors Python's
 * dateutil.relativedelta month-add-with-day-clamping behavior used by
 * journals/serializers.py's FiscalYear period generation. */

function daysInMonth(year: number, month1to12: number): number {
  return new Date(Date.UTC(year, month1to12, 0)).getUTCDate();
}

export function parseIsoDate(iso: string): { year: number; month: number; day: number } {
  const [year, month, day] = iso.slice(0, 10).split('-').map(Number);
  return { year, month, day };
}

export function formatIsoDate(d: { year: number; month: number; day: number }): string {
  return `${String(d.year).padStart(4, '0')}-${String(d.month).padStart(2, '0')}-${String(d.day).padStart(2, '0')}`;
}

export function addMonthsClamped(iso: string, months: number): string {
  const { year, month, day } = parseIsoDate(iso);
  const totalMonths = (year * 12 + (month - 1)) + months;
  const newYear = Math.floor(totalMonths / 12);
  const newMonth = (totalMonths % 12) + 1;
  const clampedDay = Math.min(day, daysInMonth(newYear, newMonth));
  return formatIsoDate({ year: newYear, month: newMonth, day: clampedDay });
}

export function addDays(iso: string, days: number): string {
  const { year, month, day } = parseIsoDate(iso);
  const utcMs = Date.UTC(year, month - 1, day) + days * 86400000;
  const d = new Date(utcMs);
  return formatIsoDate({ year: d.getUTCFullYear(), month: d.getUTCMonth() + 1, day: d.getUTCDate() });
}

export function monthYearLabel(iso: string): string {
  const { year, month } = parseIsoDate(iso);
  const names = [
    'January', 'February', 'March', 'April', 'May', 'June',
    'July', 'August', 'September', 'October', 'November', 'December',
  ];
  return `${names[month - 1]} ${year}`;
}
