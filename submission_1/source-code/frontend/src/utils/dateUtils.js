const IST_TIME_ZONE = "Asia/Kolkata";

const dateTimeFormatterIST = new Intl.DateTimeFormat("en-IN", {
  timeZone: IST_TIME_ZONE,
  day: "2-digit",
  month: "short",
  year: "numeric",
  hour: "numeric",
  minute: "2-digit",
  hour12: true,
});

const dateFormatterIST = new Intl.DateTimeFormat("en-IN", {
  timeZone: IST_TIME_ZONE,
  day: "2-digit",
  month: "short",
  year: "numeric",
});

const timeFormatterIST = new Intl.DateTimeFormat("en-IN", {
  timeZone: IST_TIME_ZONE,
  hour: "numeric",
  minute: "2-digit",
  hour12: true,
});

function normalizeMeridiem(value) {
  return value.replace(/\b(am|pm)\b/gi, (match) => match.toUpperCase());
}

function normalizeDateInput(dateValue) {
  if (dateValue === null || dateValue === undefined || dateValue === "") {
    return null;
  }

  if (typeof dateValue !== "string") {
    return dateValue;
  }

  const trimmedValue = dateValue.trim();

  if (!trimmedValue) {
    return null;
  }

  const hasTime = /T|\s+\d{1,2}:\d{2}/.test(trimmedValue);
  const hasTimezone = /(?:Z|[+-]\d{2}:?\d{2})$/i.test(trimmedValue);

  if (hasTime && !hasTimezone) {
    return `${trimmedValue.replace(" ", "T")}Z`;
  }

  return trimmedValue;
}

function getDateTimestamp(dateValue) {
  const normalizedValue = normalizeDateInput(dateValue);

  if (normalizedValue === null) {
    return null;
  }

  const timestamp = Date.parse(normalizedValue);

  return Number.isNaN(timestamp) ? null : timestamp;
}

function formatWithIST(dateValue, formatter, includeSuffix = false) {
  const timestamp = getDateTimestamp(dateValue);

  if (timestamp === null) {
    return "-";
  }

  const formattedValue = normalizeMeridiem(formatter.format(timestamp));

  return includeSuffix ? `${formattedValue} IST` : formattedValue;
}

export function formatDateTimeIST(dateValue) {
  return formatWithIST(dateValue, dateTimeFormatterIST, true);
}

export function formatDateIST(dateValue) {
  return formatWithIST(dateValue, dateFormatterIST);
}

export function formatTimeIST(dateValue) {
  return formatWithIST(dateValue, timeFormatterIST, true);
}

export function getDateTimestampISTSafe(dateValue) {
  return getDateTimestamp(dateValue) || 0;
}
