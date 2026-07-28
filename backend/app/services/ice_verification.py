import re


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


def verify_ice(ice: str) -> IceVerificationResult:
    """
    Vérification locale de l'ICE.

    Lorsque WeliPro sera disponible,
    il suffira de remplacer le contenu
    de cette fonction par un appel API.
    """

    if not ice:
        return IceVerificationResult(
            status="non_detecte",
            message="ICE non détecté."
        )

    ice = re.sub(r"\D", "", ice)

    if len(ice) != 15:
        return IceVerificationResult(
            status="format_invalide",
            message="Le format de l'ICE est invalide."
        )

    return IceVerificationResult(
        status="a_verifier",
        company_name=None,
        message="ICE valide en apparence. Vérification WeliPro en attente.",
        verification_url=None
    )