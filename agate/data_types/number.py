import warnings
from decimal import Decimal, InvalidOperation

from babel.core import Locale

from agate.data_types.base import DataType
from agate.exceptions import CastError

#: A list of currency symbols sourced from `Xe <https://www.xe.com/symbols/>`_.
DEFAULT_CURRENCY_SYMBOLS = ['؋', '$', 'ƒ', '៛', '¥', '₡', '₱', '£', '€', '¢', '﷼', '₪', '₩', '₭', '₮',
                            '₦', '฿', '₤', '₫']

POSITIVE = Decimal('1')
NEGATIVE = Decimal('-1')

#: Non-ASCII minus and plus characters that may appear in data exported from
#: financial systems. They are normalized to their ASCII equivalents before the
#: sign is interpreted so that, for example, ``"−5"`` (U+2212 MINUS SIGN) is
#: parsed the same as ``"-5"``.
UNICODE_SIGNS = {
    0x02D7: 0x002D,  # MODIFIER LETTER MINUS TRIANGULAR
    0x2052: 0x002D,  # COMMERCIAL MINUS SIGN (a minus sign, not a percent sign)
    0x207B: 0x002D,  # SUPERSCRIPT MINUS
    0x208B: 0x002D,  # SUBSCRIPT MINUS
    0x2212: 0x002D,  # MINUS SIGN
    0x2796: 0x002D,  # HEAVY MINUS SIGN
    0xFE63: 0x002D,  # SMALL HYPHEN-MINUS
    0xFF0D: 0x002D,  # FULLWIDTH HYPHEN-MINUS
    0xFE62: 0x002B,  # SMALL PLUS SIGN
    0xFF0B: 0x002B,  # FULLWIDTH PLUS SIGN
}
UNICODE_SIGN_TRANSLATION = str.maketrans(UNICODE_SIGNS)


class Number(DataType):
    """
    Data representing numbers.

    :param locale:
        A locale specification such as :code:`en_US` or :code:`de_DE` to use
        for parsing formatted numbers.
    :param group_symbol:
        A grouping symbol used in the numbers. Overrides the value provided by
        the specified :code:`locale`.
    :param decimal_symbol:
        A decimal separate symbol used in the numbers. Overrides the value
        provided by the specified :code:`locale`.
    :param currency_symbols:
        A sequence of currency symbols to strip from numbers.
    :param no_leading_zeroes:
        Whether to disallow leading zeroes.
    """
    def __init__(self, locale='en_US', group_symbol=None, decimal_symbol=None,
                 currency_symbols=DEFAULT_CURRENCY_SYMBOLS, no_leading_zeroes=None, **kwargs):
        super().__init__(**kwargs)

        self.locale = Locale.parse(locale)
        self.currency_symbols = currency_symbols
        self.no_leading_zeroes = no_leading_zeroes

        # Suppress Babel warning on Python 3.6
        # See #665
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")

            # Babel 2.14 support.
            # https://babel.pocoo.org/en/latest/changelog.html#possibly-backwards-incompatible-changes
            number_symbols = self.locale.number_symbols.get('latn', self.locale.number_symbols)
            self.group_symbol = group_symbol or number_symbols.get('group', ',')
            self.decimal_symbol = decimal_symbol or number_symbols.get('decimal', '.')

    def cast(self, d):
        """
        Cast a single value to a :class:`decimal.Decimal`.

        In addition to plain numbers, grouped numbers and numbers containing
        currency symbols, strings may use the sign conventions common in
        financial exports:

        * a leading minus sign, including Unicode minus signs such as
          ``"−5"`` (U+2212);
        * a trailing minus or plus sign, such as ``"5-"``;
        * accounting parentheses, such as ``"(5)"`` or ``"($1,234.56)"``,
          which denote a negative number.

        Parentheses and an explicit sign are mutually exclusive: values that
        combine them (such as ``"(-5)"`` or ``"-(5)"``) raise a
        :class:`.CastError`, because the two notations carry the same sign
        information and stacking them is ambiguous. Unmatched parentheses and
        empty parentheses are likewise rejected. A trailing plus sign denotes
        a positive number, mirroring the trailing minus sign.

        :returns:
            :class:`decimal.Decimal` or :code:`None`.
        """
        if isinstance(d, Decimal) or d is None:
            return d

        t = type(d)

        if t is int:
            return Decimal(d)
        if t is float:
            return Decimal(repr(d))
        if d is False:
            return Decimal(0)
        if d is True:
            return Decimal(1)
        if not isinstance(d, str):
            raise CastError('Can not parse value "%s" as Decimal.' % d)

        d = d.strip()

        if d.lower() in self.null_values:
            return None

        # Normalize Unicode minus and plus signs to their ASCII equivalents.
        d = d.translate(UNICODE_SIGN_TRANSLATION)

        # Strip currency symbols before interpreting the sign, so that symbols
        # placed outside the accounting parentheses, e.g. "$(1,234.56)", are
        # removed too.
        for symbol in self.currency_symbols:
            d = d.strip(symbol)

        d = d.strip()

        sign = POSITIVE

        # Accounting parentheses, e.g. "(1,234.56)" or "($1,234.56)", denote
        # a negative number. They may not be combined with an explicit sign.
        parenthesized = d.startswith('(') or d.endswith(')')
        if parenthesized:
            if not (d.startswith('(') and d.endswith(')')):
                raise CastError('Can not parse value "%s" as Decimal.' % d)

            d = d[1:-1].strip()

            if not d or d[0] in '-+' or d[-1] in '-+':
                raise CastError('Can not parse value "%s" as Decimal.' % d)

            sign = NEGATIVE
        elif len(d) > 0 and d[0] == '-':
            d = d[1:]
            sign = NEGATIVE
        elif len(d) > 0 and d[-1] in '-+':
            # Trailing signs, e.g. "5-" or "5+". A trailing plus is positive.
            if d[-1] == '-':
                sign = NEGATIVE
            d = d[:-1].strip()

        # Currency symbols may instead be inside the parentheses, e.g. "($5)".
        for symbol in self.currency_symbols:
            d = d.strip(symbol)

        # A percent sign may appear either outside or inside the parentheses.
        d = d.strip('%')

        d = d.replace(self.group_symbol, '')
        d = d.replace(self.decimal_symbol, '.')

        if self.no_leading_zeroes and len(d) > 1 and d[0] == '0' and d[1] != '.':
            raise CastError('Can not parse value "%s" as Decimal without leading zeroes' % d)

        try:
            return Decimal(d) * sign
        # The Decimal class will return an InvalidOperation exception on most Python implementations,
        # but PyPy3 may return a ValueError if the string is not translatable to ASCII
        except (InvalidOperation, ValueError):
            pass

        raise CastError('Can not parse value "%s" as Decimal.' % d)

    def csvify(self, d):
        return d

    def jsonify(self, d):
        if d is None:
            return d

        return float(d)
