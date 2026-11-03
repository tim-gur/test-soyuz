from app.schemas import CommercialBlock, LLMOutput, ProductInput
from app.validators import check_lengths, find_missing_fields, find_unknown_numbers


def make_product():
    return ProductInput(
        name="Манометр показывающий DM 02",
        manufacturer="Манотомь",
        specs={"диапазон измерений": "0–1,6 МПа", "класс точности": "1,5",
               "присоединение": "G1/2", "диаметр корпуса": "100 мм"},
        description="Предназначен для измерения избыточного давления.",
    )


def make_output(**kw):
    base = dict(
        seo_title="Манометр DM 02 0–1,6 МПа",
        seo_description="x" * 900,
        search_queries=["манометр dm 02", "манометр 1,6 мпа", "манометр g1/2"],
        commercial_block=CommercialBlock(
            suitable_for=["слесари"], tasks_solved=["контроль давления"]
        ),
    )
    return LLMOutput(**{**base, **kw})


def test_missing_fields_empty_input():
    assert len(find_missing_fields(ProductInput(name="Прибор"))) == 3


def test_missing_fields_full_input():
    assert find_missing_fields(make_product()) == []


def test_known_numbers_pass():
    assert find_unknown_numbers(make_product(), make_output()) == []


def test_unknown_number_caught():
    out = make_output(seo_title="Манометр DM 02 на 2,5 МПа")
    assert find_unknown_numbers(make_product(), out)


def test_title_too_long():
    assert check_lengths(make_output(seo_title="а" * 71))


def test_description_too_short():
    assert check_lengths(make_output(seo_description="x" * 500))


def test_too_few_queries():
    assert check_lengths(make_output(search_queries=["один", "два"]))