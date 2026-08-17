import re


ICE_MAROC_SEARCH_URL = (
    "https://www.icemaroc.com/index.php"
)

ICE_MAROC_VERIFIER_URL = (
    "https://www.icemaroc.com/verificateur-ice.php"
)


class IceVerificationResult:
    def __init__(
        self,
        status: str,
        company_name: str | None = None,
        message: str | None = None,
        verification_url: str | None = None,
    ):
        self.status = status
        self.company_name = company_name
        self.message = message
        self.verification_url = verification_url


def normalize_ice(ice: str | None) -> str:
    """
    Supprime les espaces, les tirets et tous les caractères
    autres que les chiffres.
    """

    if not ice:
        return ""

    return re.sub(r"\D", "", ice)


def calculate_ice_key(first_thirteen_digits: str) -> str:
    """
    Calcule la clé de contrôle correspondant aux
    deux derniers chiffres d'un ICE marocain.

    Formule :
    97 - ((13 premiers chiffres × 100) modulo 97)
    """

    number = int(first_thirteen_digits)

    calculated_key = 97 - (
        (number * 100) % 97
    )

    return str(calculated_key).zfill(2)


def verify_ice(
    ice: str | None,
) -> IceVerificationResult:
    """
    Vérifie automatiquement le format et la clé
    mathématique d'un ICE marocain.

    Cette fonction ne confirme pas encore l'existence
    de la société, car ICE Maroc ne fournit pas
    d'API publique documentée.
    """

    normalized_ice = normalize_ice(ice)

    if not normalized_ice:
        return IceVerificationResult(
            status="non_detecte",
            message=(
                "Aucun ICE n'a été détecté "
                "dans la facture."
            ),
            verification_url=None,
        )

    if len(normalized_ice) != 15:
        return IceVerificationResult(
            status="format_invalide",
            message=(
                "L'ICE doit contenir exactement "
                "15 chiffres."
            ),
            verification_url=ICE_MAROC_VERIFIER_URL,
        )

    first_thirteen_digits = normalized_ice[:13]
    provided_key = normalized_ice[13:]

    calculated_key = calculate_ice_key(
        first_thirteen_digits
    )

    if provided_key != calculated_key:
        return IceVerificationResult(
            status="cle_invalide",
            message=(
                "La clé de contrôle de l'ICE est "
                "incorrecte. "
                f"Clé trouvée : {provided_key}. "
                f"Clé attendue : {calculated_key}."
            ),
            verification_url=ICE_MAROC_VERIFIER_URL,
        )

    return IceVerificationResult(
        status="valide_mathematiquement",
        company_name=None,
        message=(
            "L'ICE contient 15 chiffres et sa clé "
            "de contrôle est correcte. "
            "L'existence de la société doit encore "
            "être confirmée dans l'annuaire ICE Maroc."
        ),
        verification_url=ICE_MAROC_SEARCH_URL,
    )