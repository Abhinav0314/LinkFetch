import json
import re
import html
from typing import Dict, Any, List, Optional
from bs4 import BeautifulSoup

from app.core.logging import logger
from app.schemas.profile import (
    ProfileData,
    Location,
    Position,
    Education,
    Skill,
    Certification,
    Language,
    ContactInfo,
    DateModel,
)


EMOJI_PATTERN = re.compile(
    "["
    "\U0001F600-\U0001F64F"  # emoticons
    "\U0001F300-\U0001F5FF"  # symbols & pictographs
    "\U0001F680-\U0001F6FF"  # transport & map symbols
    "\U0001F1E0-\U0001F1FF"  # flags
    "\U0001F900-\U0001F9FF"  # supplemental symbols
    "\U0001FA70-\U0001FAFF"  # symbols and pictographs extended
    "\U00002700-\U000027BF"  # dingbats
    "\U000024C2-\U0001F251"
    "\U0001F004-\U0001F0CF"
    "\U0001F170-\U0001F251"
    "\u200d\ufe0e\ufe0f\u200e\u200f"
    "\u25AA-\u25FE"          # geometric shapes / black small square / bullet symbols
    "\u2022\u2023\u25E6\u2043\u2219" # bullets
    "\U0001F3FB-\U0001F3FF"  # skin tones
    "]+",
    flags=re.UNICODE,
)


def clean_text_field(val: Optional[str]) -> Optional[str]:
    """Strips decorative emojis, dingbats, and bullet symbols from text fields."""
    if not val:
        return None
    cleaned = EMOJI_PATTERN.sub(" ", str(val))
    cleaned = re.sub(r"\s+", " ", cleaned)
    cleaned = cleaned.strip(" \t\r\n·-–—|•▪")
    return cleaned if cleaned else None


def is_masked(val: Any) -> bool:
    """Checks if a string or structure contains LinkedIn guest-redaction asterisks or empty placeholders."""
    if val is None:
        return True
    if isinstance(val, str):
        c = val.strip()
        if not c or c == "-" or "***" in c or "*****" in c:
            return True
        return False
    if isinstance(val, list):
        return len(val) == 0 or all(is_masked(x) for x in val)
    return False


class PublicProfileParser:
    """Parses public LinkedIn profile HTML containing Schema.org JSON-LD and OpenGraph tags."""

    @staticmethod
    def parse(html_content: str, public_id: str, profile_url: str) -> ProfileData:
        soup = BeautifulSoup(html_content, "lxml")

        # 1. Extract Schema.org JSON-LD scripts (supporting root object, lists, and @graph structures)
        json_ld_data: Dict[str, Any] = {}
        for script in soup.find_all("script", type="application/ld+json"):
            try:
                content = script.string or script.get_text()
                if not content:
                    continue
                parsed = json.loads(content)
                json_ld_data = PublicProfileParser._find_person_json_ld(parsed)
                if json_ld_data:
                    break
            except Exception as e:
                logger.debug(f"Failed to parse JSON-LD script: {e}")

        # 2. Extract OpenGraph & Meta tags
        og_title = (
            PublicProfileParser._get_meta(soup, "og:title")
            or PublicProfileParser._get_meta(soup, "twitter:title")
        )
        og_desc = (
            PublicProfileParser._get_meta(soup, "og:description")
            or PublicProfileParser._get_meta(soup, "description")
            or PublicProfileParser._get_meta(soup, "twitter:description")
        )
        og_image = (
            PublicProfileParser._get_meta(soup, "og:image")
            or PublicProfileParser._get_meta(soup, "twitter:image")
        )
        page_title = soup.title.string.strip() if soup.title and soup.title.string else ""

        # 3. Parse structured information embedded in og:description
        og_extracted: Dict[str, str] = {}
        if og_desc:
            cleaned_og = html.unescape(og_desc)
            cleaned_og = re.sub(r'[\u00a0\xa0\u2022\u00b7\ufffd\x7f-\xff]+', ' | ', cleaned_og)
            parts = [p.strip() for p in cleaned_og.split('|') if p.strip()]
            summary_parts = []
            for p in parts:
                if p.startswith("Experience:"):
                    og_extracted["experience"] = p.replace("Experience:", "").strip()
                elif p.startswith("Education:"):
                    og_extracted["education"] = p.replace("Education:", "").strip()
                elif p.startswith("Location:"):
                    og_extracted["location"] = p.replace("Location:", "").strip()
                elif "connections on LinkedIn" in p or "followers on LinkedIn" in p or "profile on LinkedIn" in p:
                    continue
                else:
                    summary_parts.append(p)
            if summary_parts:
                og_extracted["summary"] = " ".join(summary_parts).strip()

        # 4. Determine Full Name
        full_name = json_ld_data.get("name") if not is_masked(json_ld_data.get("name")) else None
        first_name = json_ld_data.get("givenName") if not is_masked(json_ld_data.get("givenName")) else None
        last_name = json_ld_data.get("familyName") if not is_masked(json_ld_data.get("familyName")) else None

        if not first_name:
            fn_meta = PublicProfileParser._get_meta(soup, "profile:first_name")
            if fn_meta and not is_masked(fn_meta):
                first_name = fn_meta
        if not last_name:
            ln_meta = PublicProfileParser._get_meta(soup, "profile:last_name")
            if ln_meta and not is_masked(ln_meta):
                last_name = ln_meta

        if not full_name and og_title:
            cleaned_title = re.sub(r"\s*\|\s*LinkedIn.*$", "", og_title).strip()
            if " - " in cleaned_title:
                full_name = cleaned_title.split(" - ")[0].strip()
            else:
                full_name = cleaned_title.strip()

        if not full_name and page_title:
            cleaned_title = re.sub(r"\s*\|\s*LinkedIn.*$", "", page_title).strip()
            if " - " in cleaned_title:
                full_name = cleaned_title.split(" - ")[0].strip()
            else:
                full_name = cleaned_title.strip()

        if not full_name or is_masked(full_name):
            full_name = public_id

        if not first_name and full_name:
            parts = full_name.split()
            first_name = parts[0] if parts else ""
            last_name = " ".join(parts[1:]) if len(parts) > 1 else ""

        # 5. Headline / Job Title
        headline = None
        json_headline = json_ld_data.get("jobTitle")
        if isinstance(json_headline, list):
            valid_h = [h for h in json_headline if isinstance(h, str) and not is_masked(h)]
            if valid_h:
                headline = valid_h[0]
        elif isinstance(json_headline, str) and not is_masked(json_headline):
            headline = json_headline

        if not headline and og_extracted.get("summary"):
            m = re.search(r"^As\s+(.+?)\s+of\s+([^,]+)", og_extracted["summary"], re.IGNORECASE)
            if m:
                headline = f"{m.group(1).strip().capitalize()} at {m.group(2).strip()}"
            else:
                m2 = re.search(r"^As\s+(.+?)\s+at\s+([^,]+)", og_extracted["summary"], re.IGNORECASE)
                if m2:
                    headline = f"{m2.group(1).strip().capitalize()} at {m2.group(2).strip()}"

        if not headline and og_title:
            cleaned_title = re.sub(r"\s*\|\s*LinkedIn.*$", "", og_title).strip()
            parts = cleaned_title.split(" - ")
            if len(parts) > 1 and not is_masked(parts[1]):
                headline = parts[1].strip()

        if not headline:
            headline = og_extracted.get("summary") or og_desc

        # 6. Location
        location_obj = None
        addr = json_ld_data.get("address")
        if isinstance(addr, dict):
            city = addr.get("addressLocality") if not is_masked(addr.get("addressLocality")) else None
            region = addr.get("addressRegion") if not is_masked(addr.get("addressRegion")) else None
            country = addr.get("addressCountry") if not is_masked(addr.get("addressCountry")) else None
            loc_parts = []
            if city:
                loc_parts.append(city)
            if region and region not in (city or ""):
                loc_parts.append(region)
            if country and country not in (city or "") and country not in ("US", "USA"):
                loc_parts.append(country)
            raw_loc = ", ".join(loc_parts) if loc_parts else None
            location_obj = Location(raw=raw_loc, city=city, region=region, country=country)
        elif isinstance(addr, str) and not is_masked(addr):
            location_obj = Location(raw=addr)

        if not location_obj and og_extracted.get("location"):
            loc_str = og_extracted["location"]
            location_obj = Location(raw=loc_str, city=loc_str)

        # 7. About / Description
        about = json_ld_data.get("description") if not is_masked(json_ld_data.get("description")) else None
        if not about and og_extracted.get("summary"):
            about = og_extracted["summary"]

        if about:
            about = html.unescape(about)
            about = re.sub(r'[\u00a0\xa0\ufffd\x7f-\xff]+', ' ', about)
            about = re.sub(r"\s*Experience:.*$", "", about, flags=re.IGNORECASE)
            about = re.sub(r"\s*View\s+.*?\s+profile on LinkedIn.*$", "", about, flags=re.IGNORECASE)
            about = about.strip()

        # 8. Profile Picture & Background Banner
        profile_picture_url = None
        img_field = json_ld_data.get("image")
        if isinstance(img_field, dict):
            profile_picture_url = img_field.get("contentUrl") or img_field.get("url")
        elif isinstance(img_field, str) and not is_masked(img_field):
            profile_picture_url = img_field
        if not profile_picture_url and og_image and "static.licdn.com" not in og_image:
            profile_picture_url = og_image

        background_picture_url = None

        # Strategy 1: Direct CSS selector matching for banner image elements
        banner_selectors = [
            ".top-card-layout__background-image img",
            "img.cover-img",
            "[data-section='cover-image'] img",
            ".profile-background-image__image",
            ".cover-img__image",
            ".profile-background-image img",
            ".pv-top-card--photo-resize img.profile-background-image__image",
            "section.top-card-layout img[data-delayed-url]",
            ".top-card__background-image img",
            ".background-cover-image img",
        ]
        for selector in banner_selectors:
            bg_el = soup.select_one(selector)
            if bg_el:
                src = bg_el.get("src") or bg_el.get("data-delayed-url") or bg_el.get("data-src")
                if src and not is_masked(src) and "static.licdn.com" not in src:
                    background_picture_url = src
                    break

        # Strategy 2: Find divs/sections with inline background-image CSS
        if not background_picture_url:
            for el in soup.select(".top-card-layout__background, .cover-img, [class*='background'], [class*='banner'], [class*='cover']"):
                style = el.get("style", "")
                if "background-image" in style:
                    m = re.search(r'url\(["\']?(https?://[^"\')\s]+)["\']?\)', style)
                    if m and "static.licdn.com" not in m.group(1):
                        background_picture_url = m.group(1)
                        break

        # Strategy 3: Extract from LinkedIn's embedded <code> JSON data blocks
        if not background_picture_url:
            for code_el in soup.find_all("code"):
                try:
                    code_text = code_el.string or code_el.get_text()
                    if not code_text or "backgroundImage" not in code_text:
                        continue
                    data = json.loads(code_text)
                    bg_url = PublicProfileParser._find_background_image_in_data(data)
                    if bg_url:
                        background_picture_url = bg_url
                        break
                except Exception as exc:
                    logger.debug(f"Error parsing embedded code block: {exc}")

        # 9. Experience (filter out asterisk-masked entries & deduplicate)
        experiences: List[Position] = []
        seen_exp = set()

        def add_public_exp(title_val: str, comp_val: str, comp_url_val: Optional[str] = None, desc_val: Optional[str] = None, is_curr: bool = False):
            if not comp_val or is_masked(comp_val):
                return
            t_clean = (title_val or "Position").strip()
            c_clean = comp_val.strip()
            key = f"{t_clean.lower()}_{c_clean.lower()}"
            if key in seen_exp:
                return
            seen_exp.add(key)
            experiences.append(Position(
                title=t_clean,
                company_name=c_clean,
                company_url=comp_url_val,
                description=desc_val,
                is_current=is_curr,
            ))

        # From HTML sections first (richer description/titles)
        for item in soup.select(".experience-item, [data-section='experience'] li, [data-section='experience'] .profile-section-card, .experience__list li"):
            try:
                title_el = item.select_one(".experience-item__title, h3, .profile-section-card__title")
                comp_el = item.select_one(".experience-item__subtitle, h4, .profile-section-card__subtitle")
                desc_el = item.select_one(".experience-item__description, p")
                if comp_el and comp_el.text.strip() and not is_masked(comp_el.text):
                    title_txt = title_el.text.strip() if title_el else (headline or "Professional")
                    if not is_masked(title_txt):
                        add_public_exp(
                            title_val=title_txt,
                            comp_val=comp_el.text.strip(),
                            desc_val=desc_el.text.strip() if desc_el else None,
                            is_curr=False,
                        )
            except Exception as exc:
                logger.debug(f"Error parsing public experience item: {exc}")

        # From JSON-LD worksFor
        works_for = json_ld_data.get("worksFor")
        if isinstance(works_for, list):
            for org in works_for:
                if isinstance(org, dict):
                    add_public_exp(
                        title_val=headline or "Member",
                        comp_val=org.get("name", ""),
                        comp_url_val=org.get("url") or org.get("sameAs"),
                        is_curr=True,
                    )
        elif isinstance(works_for, dict):
            add_public_exp(
                title_val=headline or "Member",
                comp_val=works_for.get("name", ""),
                comp_url_val=works_for.get("url") or works_for.get("sameAs"),
                is_curr=True,
            )

        # From OG description
        if not experiences and og_extracted.get("experience"):
            add_public_exp(
                title_val=headline or "Member",
                comp_val=og_extracted["experience"],
                is_curr=True,
            )

        # 10. Education (filter out masked entries & deduplicate)
        educations: List[Education] = []
        seen_edu = set()

        def add_public_edu(school_val: str, degree_val: Optional[str] = None, school_url_val: Optional[str] = None, sy: Optional[int] = None, ey: Optional[int] = None):
            if not school_val or is_masked(school_val):
                return
            s_clean = school_val.strip()
            d_clean = degree_val.strip() if degree_val else ""
            key = f"{s_clean.lower()}_{d_clean.lower()}_{sy or ''}"
            if key in seen_edu:
                return
            seen_edu.add(key)
            educations.append(Education(
                school_name=s_clean,
                degree_name=d_clean if d_clean else None,
                school_url=school_url_val,
                start_year=sy,
                end_year=ey,
            ))

        # From HTML sections
        for item in soup.select(".education-item, [data-section='educations'] li, .education__list li, .education-section li"):
            try:
                school_el = item.select_one(".education-item__title, h3, .profile-section-card__title")
                degree_el = item.select_one(".education-item__subtitle, h4, .profile-section-card__subtitle")
                if school_el and school_el.text.strip() and not is_masked(school_el.text):
                    add_public_edu(
                        school_val=school_el.text.strip(),
                        degree_val=degree_el.text.strip() if degree_el else None,
                    )
            except Exception as exc:
                logger.debug(f"Error parsing public education item: {exc}")

        # From JSON-LD alumniOf
        alumni_of = json_ld_data.get("alumniOf")
        if isinstance(alumni_of, list):
            for school in alumni_of:
                if isinstance(school, dict):
                    member = school.get("member", {}) if isinstance(school.get("member"), dict) else {}
                    add_public_edu(
                        school_val=school.get("name", ""),
                        school_url_val=school.get("url") or school.get("sameAs"),
                        sy=member.get("startDate") if isinstance(member.get("startDate"), int) else None,
                        ey=member.get("endDate") if isinstance(member.get("endDate"), int) else None,
                    )
        elif isinstance(alumni_of, dict):
            member = alumni_of.get("member", {}) if isinstance(alumni_of.get("member"), dict) else {}
            add_public_edu(
                school_val=alumni_of.get("name", ""),
                school_url_val=alumni_of.get("url") or alumni_of.get("sameAs"),
                sy=member.get("startDate") if isinstance(member.get("startDate"), int) else None,
                ey=member.get("endDate") if isinstance(member.get("endDate"), int) else None,
            )

        # From OG description
        if not educations and og_extracted.get("education"):
            add_public_edu(school_val=og_extracted["education"])

        # 11. Websites
        websites: List[str] = []
        same_as = json_ld_data.get("sameAs")
        if isinstance(same_as, list):
            websites.extend([str(s) for s in same_as if isinstance(s, str) and not is_masked(s)])
        elif isinstance(same_as, str) and not is_masked(same_as):
            websites.append(same_as)

        # 12. Skills (public HTML parsing & intelligent text extraction)
        skills: List[Skill] = []
        for item in soup.select(
            "[data-section='skills'] li, "
            "[data-section='skills'] .profile-section-card, "
            ".skills-section li, "
            ".skills__list li, "
            ".pv-skill-categories-section li"
        ):
            try:
                name_el = item.select_one(
                    ".profile-section-card__title, h3, "
                    ".pv-skill-category-entity__name span, "
                    ".skill-categories-card__name, span"
                )
                if name_el and name_el.text.strip() and not is_masked(name_el.text):
                    skill_name = name_el.text.strip()
                    if not any(s.name.lower() == skill_name.lower() for s in skills):
                        skills.append(Skill(name=skill_name))
            except Exception as exc:
                logger.debug(f"Error parsing public skill item: {exc}")

        # If public HTML masked the standalone skills section, extract mentioned skills from summary/about/headline
        if not skills:
            skills = PublicProfileParser._extract_skills_from_text(f"{about or ''} {headline or ''}")

        # 13. Languages (public HTML parsing)
        languages: List[Language] = []
        for item in soup.select(
            "[data-section='languages'] li, "
            "[data-section='languages'] .profile-section-card, "
            ".languages-section li"
        ):
            try:
                name_el = item.select_one(".profile-section-card__title, h3, span")
                prof_el = item.select_one(".profile-section-card__subtitle, h4")
                if name_el and name_el.text.strip() and not is_masked(name_el.text):
                    lang_name = name_el.text.strip()
                    proficiency = prof_el.text.strip() if prof_el else None
                    if not any(l.name.lower() == lang_name.lower() for l in languages):
                        languages.append(Language(
                            name=lang_name,
                            proficiency=proficiency,
                        ))
            except Exception as exc:
                logger.debug(f"Error parsing public language item: {exc}")

        # 14. Certifications (public HTML parsing)
        certifications: List[Certification] = []
        for item in soup.select(
            "[data-section='certifications'] li, "
            "[data-section='certifications'] .profile-section-card, "
            ".certifications-section li"
        ):
            try:
                name_el = item.select_one(".profile-section-card__title, h3")
                auth_el = item.select_one(".profile-section-card__subtitle, h4")
                if name_el and name_el.text.strip() and not is_masked(name_el.text):
                    cert_name = name_el.text.strip()
                    authority = auth_el.text.strip() if auth_el else None
                    if not any(c.name.lower() == cert_name.lower() for c in certifications):
                        certifications.append(Certification(
                            name=cert_name,
                            authority=authority,
                        ))
            except Exception as exc:
                logger.debug(f"Error parsing public certification item: {exc}")

        return ProfileData(
            public_id=public_id,
            profile_url=profile_url,
            first_name=first_name,
            last_name=last_name,
            full_name=full_name,
            headline=headline,
            location=location_obj,
            about=about,
            profile_picture_url=profile_picture_url,
            background_picture_url=background_picture_url,
            experience=experiences,
            education=educations,
            skills=skills,
            certifications=certifications,
            languages=languages,
            contact_info=ContactInfo(websites=websites),
        )

    @staticmethod
    def _extract_skills_from_text(text: Optional[str]) -> List[Skill]:
        """Extracts technical, domain, and stated skills from profile summary / about text."""
        if not text:
            return []

        extracted: List[Skill] = []
        seen = set()

        # 1. Search for explicit listed skills patterns (e.g. "Skills: Python, FastAPI, React")
        m = re.search(r'(?:Skills|Technologies|Core Competencies|Specialties|Tech Stack|Expertise):\s*([^.\n]+)', text, re.IGNORECASE)
        if m:
            raw_list = m.group(1)
            tokens = re.split(r'[,|•·;]+', raw_list)
            for t in tokens:
                clean = t.strip()
                if 1 < len(clean) < 40 and not is_masked(clean):
                    if clean.lower() not in seen:
                        seen.add(clean.lower())
                        extracted.append(Skill(name=clean))

        # 2. Match standard technical and leadership skills keywords
        COMMON_SKILL_KEYWORDS = [
            "Python", "JavaScript", "TypeScript", "FastAPI", "Django", "Flask", "React", "Next.js",
            "Node.js", "Vue.js", "Angular", "HTML5", "CSS3", "Tailwind CSS",
            "Java", "Spring Boot", "Kotlin", "Swift", "C++", "C#", ".NET", "Golang", "Rust",
            "PHP", "Ruby", "Ruby on Rails", "SQL", "PostgreSQL", "MySQL", "MongoDB", "Redis",
            "GraphQL", "REST APIs", "Docker", "Kubernetes", "AWS", "Amazon Web Services",
            "Azure", "Google Cloud", "GCP", "DevOps", "CI/CD", "Git", "GitHub", "Linux",
            "Machine Learning", "Deep Learning", "Artificial Intelligence", "Natural Language Processing",
            "Data Science", "Data Analysis", "Computer Vision", "Microservices", "System Design",
            "Agile Methodologies", "Scrum", "Product Management", "Project Management",
            "Cloud Computing", "Distributed Systems", "Cybersecurity", "Network Security", "Strategic Leadership"
        ]

        text_lower = f" {text.lower()} "
        for kw in COMMON_SKILL_KEYWORDS:
            pattern = r'(?:\b|[^a-zA-Z0-9])' + re.escape(kw.lower()) + r'(?:\b|[^a-zA-Z0-9])'
            if re.search(pattern, text_lower) and kw.lower() not in seen:
                seen.add(kw.lower())
                extracted.append(Skill(name=kw))
                if len(extracted) >= 20:
                    break

        return extracted

    @staticmethod
    def _find_person_json_ld(parsed: Any) -> Dict[str, Any]:
        """Recursively traverses parsed JSON-LD structures looking for a Person entity."""
        if isinstance(parsed, dict):
            if parsed.get("@type") == "Person":
                return parsed
            if "@graph" in parsed and isinstance(parsed["@graph"], list):
                res = PublicProfileParser._find_person_json_ld(parsed["@graph"])
                if res:
                    return res
        elif isinstance(parsed, list):
            for item in parsed:
                res = PublicProfileParser._find_person_json_ld(item)
                if res:
                    return res
        return {}

    @staticmethod
    def _get_meta(soup: BeautifulSoup, property_name: str) -> Optional[str]:
        tag = soup.find("meta", property=property_name) or soup.find("meta", attrs={"name": property_name})
        if tag and tag.get("content"):
            return tag["content"].strip()
        return None

    @staticmethod
    def _find_background_image_in_data(data: Any) -> Optional[str]:
        """Traverses embedded JSON or data objects looking for background/cover image URLs or vectors."""
        if not data:
            return None
        if isinstance(data, dict):
            for key in ("backgroundImage", "backgroundPicture", "coverPicture", "coverImage", "photoFilterPicture"):
                if key in data:
                    res = VoyagerGraphParser._resolve_image_vector(data[key])
                    if res:
                        return res
            for v in data.values():
                res = PublicProfileParser._find_background_image_in_data(v)
                if res:
                    return res
        elif isinstance(data, list):
            for item in data:
                res = PublicProfileParser._find_background_image_in_data(item)
                if res:
                    return res
        return None


class VoyagerGraphParser:
    """
    Parses LinkedIn's internal normalized Voyager API graph response.
    Resolves included entity graphs (miniProfiles, positions, educations, skills, certs, images).
    """

    @staticmethod
    def parse(raw_json: Dict[str, Any], public_id: str, profile_url: str) -> ProfileData:
        included = raw_json.get("included", [])
        data = raw_json.get("data", {})

        # Build entity map by URN and type
        entity_map: Dict[str, Dict[str, Any]] = {}
        for item in included:
            if isinstance(item, dict):
                entity_urn = item.get("entityUrn") or item.get("urn")
                if entity_urn:
                    entity_map[entity_urn] = item

        # Find primary profile entity matching public_id
        profile_entity = VoyagerGraphParser._find_primary_profile(data, included, public_id)

        # Extract basic info
        first_name = profile_entity.get("firstName")
        last_name = profile_entity.get("lastName")
        full_name = f"{first_name or ''} {last_name or ''}".strip()
        if not full_name or is_masked(full_name):
            full_name = (
                profile_entity.get("miniProfile", {}).get("firstName", "")
                + " "
                + profile_entity.get("miniProfile", {}).get("lastName", "")
            )
            full_name = full_name.strip() or public_id

        headline = profile_entity.get("headline") or profile_entity.get("miniProfile", {}).get("occupation")
        if is_masked(headline):
            headline = None

        about = profile_entity.get("summary") or profile_entity.get("miniProfile", {}).get("summary")
        if is_masked(about):
            about = None

        urn_id = profile_entity.get("entityUrn") or profile_entity.get("urn")

        # Location extraction
        geo_name = (
            profile_entity.get("geoLocationName")
            or profile_entity.get("locationName")
            or profile_entity.get("geoCountryName")
        )
        location_obj = Location(raw=geo_name) if geo_name and not is_masked(geo_name) else None

        # Images extraction strictly from the target profile entity
        # 1. Profile Avatar (PhotoFilterPicture, Picture, DisplayImage)
        profile_picture_url = VoyagerGraphParser._resolve_image_vector(
            profile_entity.get("picture")
            or profile_entity.get("profilePicture")
            or profile_entity.get("photoFilterPicture")
            or profile_entity.get("displayImage")
            or profile_entity.get("miniProfile", {}).get("picture")
            or profile_entity.get("miniProfile", {}).get("profilePicture")
        )

        # If picture reference is an URN in entity_map, resolve it
        pic_urn = profile_entity.get("photoFilterPicture") or profile_entity.get("picture")
        if not profile_picture_url and isinstance(pic_urn, str) and pic_urn in entity_map:
            profile_picture_url = VoyagerGraphParser._resolve_image_vector(entity_map[pic_urn])

        # 2. Background Banner (BackgroundPicture, BackgroundImage, CoverPicture)
        background_picture_url = VoyagerGraphParser._resolve_image_vector(
            profile_entity.get("backgroundPicture")
            or profile_entity.get("backgroundImage")
            or profile_entity.get("coverPicture")
            or profile_entity.get("miniProfile", {}).get("backgroundImage")
            or profile_entity.get("miniProfile", {}).get("backgroundPicture")
        )

        bg_urn = profile_entity.get("backgroundPicture") or profile_entity.get("backgroundImage")
        if not background_picture_url and isinstance(bg_urn, str) and bg_urn in entity_map:
            background_picture_url = VoyagerGraphParser._resolve_image_vector(entity_map[bg_urn])

        # Experience extraction
        experience = VoyagerGraphParser._extract_experience(profile_entity, entity_map, included)

        # Education extraction
        education = VoyagerGraphParser._extract_education(profile_entity, entity_map, included)

        # Skills extraction
        skills = VoyagerGraphParser._extract_skills(profile_entity, entity_map, included)

        # Certifications extraction
        certifications = VoyagerGraphParser._extract_certifications(profile_entity, entity_map, included)

        # Languages extraction
        languages = VoyagerGraphParser._extract_languages(profile_entity, entity_map, included)

        # Contact Info extraction
        contact_info = VoyagerGraphParser._extract_contact_info(profile_entity, entity_map, included)

        return ProfileData(
            public_id=public_id,
            urn_id=urn_id,
            profile_url=profile_url,
            first_name=first_name,
            last_name=last_name,
            full_name=full_name,
            headline=headline,
            location=location_obj,
            about=about,
            profile_picture_url=profile_picture_url,
            background_picture_url=background_picture_url,
            experience=experience,
            education=education,
            skills=skills,
            certifications=certifications,
            languages=languages,
            contact_info=contact_info,
        )

    @staticmethod
    def _find_primary_profile(data: Dict[str, Any], included: List[Dict[str, Any]], public_id: str) -> Dict[str, Any]:
        """Identifies the target profile object matching public_id within data or included entities."""
        clean_target_id = public_id.lower().strip().strip("/")

        # 1. Check root data object
        if isinstance(data, dict):
            if "$type" in data and ("Profile" in data["$type"] or "miniProfile" in data):
                pub_id = str(data.get("publicIdentifier") or "").lower()
                if pub_id == clean_target_id or not pub_id:
                    return data
            if "elements" in data and len(data["elements"]) > 0:
                for el in data["elements"]:
                    if isinstance(el, dict):
                        pub_id = str(el.get("publicIdentifier") or "").lower()
                        if pub_id == clean_target_id:
                            return el
                # Fallback to first element if none matched publicIdentifier
                if isinstance(data["elements"][0], dict):
                    return data["elements"][0]

        # 2. Match exact publicIdentifier in included
        for item in included:
            if not isinstance(item, dict):
                continue
            type_str = item.get("$type", "")
            if "Profile" in type_str:
                pub_id = str(item.get("publicIdentifier") or "").lower()
                if pub_id and pub_id == clean_target_id:
                    return item

        # 3. Match public_id in entityUrn in included
        for item in included:
            if not isinstance(item, dict):
                continue
            type_str = item.get("$type", "")
            if "Profile" in type_str:
                urn = str(item.get("entityUrn") or item.get("urn") or "").lower()
                if clean_target_id in urn:
                    return item

        # 4. Fallback to first full Profile entity (preferring non-mini Profile)
        for item in included:
            if not isinstance(item, dict):
                continue
            type_str = item.get("$type", "")
            if "Profile" in type_str and "MiniProfile" not in type_str:
                return item

        # 5. Fallback to first miniProfile
        for item in included:
            if isinstance(item, dict) and "MiniProfile" in item.get("$type", ""):
                return item

        return data if isinstance(data, dict) else {}

    @staticmethod
    def _resolve_image_vector(picture_obj: Any) -> Optional[str]:
        """Builds high-resolution image URL from any LinkedIn image or vector artifact structure."""
        if not picture_obj:
            return None

        # Direct string URL if present
        if isinstance(picture_obj, str) and picture_obj.startswith("http"):
            return picture_obj

        if not isinstance(picture_obj, (dict, list)):
            return None

        # Direct URL key if present
        if isinstance(picture_obj, dict) and "url" in picture_obj and isinstance(picture_obj["url"], str):
            return picture_obj["url"]

        # Recursive search for a dictionary containing 'rootUrl' and 'artifacts'
        vector = VoyagerGraphParser._find_vector_image(picture_obj)
        if not vector or not isinstance(vector, dict):
            return None

        root_url = vector.get("rootUrl", "")
        artifacts = vector.get("artifacts", [])
        if not root_url or not artifacts:
            return None

        # Pick largest artifact by width (or height)
        largest = max(artifacts, key=lambda a: a.get("width", 0) if isinstance(a, dict) else 0)
        segment = largest.get("fileIdentifyingUrlPathSegment", "")
        return f"{root_url}{segment}" if segment else None

    @staticmethod
    def _find_vector_image(obj: Any) -> Optional[Dict[str, Any]]:
        """Recursively finds a dictionary with 'rootUrl' and 'artifacts'."""
        if isinstance(obj, dict):
            if "rootUrl" in obj and "artifacts" in obj:
                return obj
            for v in obj.values():
                res = VoyagerGraphParser._find_vector_image(v)
                if res:
                    return res
        elif isinstance(obj, list):
            for item in obj:
                res = VoyagerGraphParser._find_vector_image(item)
                if res:
                    return res
        return None

    @staticmethod
    def _extract_experience(profile: Dict[str, Any], entity_map: Dict[str, Any], included: List[Dict[str, Any]]) -> List[Position]:
        positions: List[Position] = []

        def add_position(p: Dict[str, Any]):
            if not isinstance(p, dict):
                return
            title = p.get("title") or p.get("jobTitle") or p.get("miniPosition", {}).get("title") or "Position"
            company_name = (
                p.get("companyName")
                or p.get("company", {}).get("name")
                or p.get("miniCompany", {}).get("name")
                or p.get("name")
                or "Organization"
            )

            company_urn = p.get("companyUrn") or p.get("company", {}).get("entityUrn") or p.get("company", {}).get("universalName")
            if (not company_name or company_name == "Organization") and company_urn and company_urn in entity_map:
                comp_entity = entity_map[company_urn]
                company_name = comp_entity.get("name") or comp_entity.get("universalName") or company_name

            if is_masked(title) and is_masked(company_name):
                return

            company_logo = None
            if company_urn and company_urn in entity_map:
                comp_entity = entity_map[company_urn]
                company_logo = VoyagerGraphParser._resolve_image_vector(comp_entity.get("logo"))
            if not company_logo:
                company_logo = VoyagerGraphParser._resolve_image_vector(p.get("company", {}).get("logo") or p.get("logo"))

            time_period = p.get("timePeriod") or p.get("dateRange") or p.get("time_period") or {}
            start_date = VoyagerGraphParser._parse_date(
                time_period.get("startDate") or time_period.get("start") or p.get("startDate") or p.get("start") or p.get("startYear")
            )
            end_date = VoyagerGraphParser._parse_date(
                time_period.get("endDate") or time_period.get("end") or p.get("endDate") or p.get("end") or p.get("endYear")
            )

            if p.get("isCurrent") is not None:
                is_current = bool(p["isCurrent"])
            elif start_date and not end_date:
                is_current = True
            else:
                is_current = False

            t_clean = clean_text_field(title) if not is_masked(title) else "Position"
            c_clean = clean_text_field(company_name) if not is_masked(company_name) else "Organization"
            loc_clean = clean_text_field(p.get("locationName") or p.get("geoLocationName") or (p.get("location", {}).get("name") if isinstance(p.get("location"), dict) else None))

            if not t_clean:
                t_clean = "Position"
            if not c_clean:
                c_clean = "Organization"

            # Check if this position already exists in positions list to merge/update
            for existing in positions:
                if existing.company_name.lower() == c_clean.lower() and (existing.title.lower() == t_clean.lower() or existing.title.lower() == "position" or t_clean.lower() == "position"):
                    if not existing.start_date and start_date:
                        existing.start_date = start_date
                        existing.end_date = end_date
                        existing.is_current = is_current
                    if (existing.title.lower() == "position" or not existing.title) and t_clean.lower() != "position":
                        existing.title = t_clean
                    if not existing.company_logo_url and company_logo:
                        existing.company_logo_url = company_logo
                    if not existing.description and p.get("description"):
                        existing.description = p.get("description")
                    if not existing.location and loc_clean:
                        existing.location = loc_clean
                    return

            positions.append(Position(
                title=t_clean,
                company_name=c_clean,
                company_url=f"https://www.linkedin.com/company/{company_urn.split(':')[-1]}" if company_urn and ":" in company_urn else None,
                company_logo_url=company_logo,
                company_urn=company_urn,
                location=loc_clean,
                start_date=start_date,
                end_date=end_date,
                is_current=is_current,
                description=p.get("description") or p.get("summary"),
                employment_type=p.get("employmentType"),
            ))

        # 1. Profile entity direct collections
        for container_key in ("positionView", "positions", "positionGroupView", "profilePositions"):
            container = profile.get(container_key)
            if isinstance(container, dict):
                for el in container.get("elements", []):
                    add_position(el)
                    for sub_pos in el.get("positions", []):
                        add_position(sub_pos)

        # 2. Included items (Positions and PositionGroups)
        for item in included:
            if not isinstance(item, dict):
                continue
            type_str = item.get("$type", "")
            if "PositionGroup" in type_str:
                for sub_pos in item.get("positions", []):
                    add_position(sub_pos)
                for sub_pos in item.get("elements", []):
                    add_position(sub_pos)
                if not item.get("positions") and not item.get("elements") and item.get("title"):
                    add_position(item)
            elif "Position" in type_str:
                add_position(item)
                for sub_pos in item.get("positions", []):
                    add_position(sub_pos)

        # Sort reverse-chronologically: Current roles first, then newest start/end dates
        def _exp_sort_key(p: Position):
            is_curr = 1 if p.is_current else 0
            end_y = 9999 if p.is_current else (p.end_date.year if p.end_date and p.end_date.year else 0)
            end_m = 99 if p.is_current else (p.end_date.month if p.end_date and p.end_date.month else 0)
            start_y = p.start_date.year if p.start_date and p.start_date.year else 0
            start_m = p.start_date.month if p.start_date and p.start_date.month else 0
            return (is_curr, end_y, start_y, end_m, start_m)

        positions.sort(key=_exp_sort_key, reverse=True)
        return positions

    @staticmethod
    def _extract_education(profile: Dict[str, Any], entity_map: Dict[str, Any], included: List[Dict[str, Any]]) -> List[Education]:
        educations: List[Education] = []

        def add_edu(e: Dict[str, Any]):
            if not isinstance(e, dict):
                return
            school_name = (
                e.get("schoolName")
                or e.get("school", {}).get("name")
                or e.get("miniSchool", {}).get("name")
                or e.get("name")
                or "Institution"
            )
            school_urn = e.get("schoolUrn") or e.get("school", {}).get("entityUrn")
            if (not school_name or school_name == "Institution") and school_urn and school_urn in entity_map:
                school_entity = entity_map[school_urn]
                school_name = school_entity.get("name") or school_name

            if is_masked(school_name):
                return

            school_logo = None
            if school_urn and school_urn in entity_map:
                school_entity = entity_map[school_urn]
                school_logo = VoyagerGraphParser._resolve_image_vector(school_entity.get("logo"))
            if not school_logo:
                school_logo = VoyagerGraphParser._resolve_image_vector(e.get("school", {}).get("logo") or e.get("logo"))

            time_period = e.get("timePeriod") or e.get("dateRange") or e.get("time_period") or {}
            start_d = VoyagerGraphParser._parse_date(
                time_period.get("startDate") or time_period.get("start") or e.get("startDate") or e.get("start") or e.get("startYear")
            )
            end_d = VoyagerGraphParser._parse_date(
                time_period.get("endDate") or time_period.get("end") or e.get("endDate") or e.get("end") or e.get("endYear")
            )

            start_year = start_d.year if start_d else (e.get("startYear") if isinstance(e.get("startYear"), int) else None)
            end_year = end_d.year if end_d else (e.get("endYear") if isinstance(e.get("endYear"), int) else None)

            field_of_study = e.get("fieldOfStudy") or e.get("major")
            if isinstance(field_of_study, list):
                field_of_study = ", ".join(str(f) for f in field_of_study if f)

            s_clean = clean_text_field(school_name) or "Institution"
            deg_clean = clean_text_field(e.get("degreeName") or e.get("degree"))
            fos_clean = clean_text_field(field_of_study)
            act_clean = clean_text_field(e.get("activities"))
            desc_clean = clean_text_field(e.get("description"))

            # Merge with existing if same school
            for existing in educations:
                if existing.school_name.lower() == s_clean.lower():
                    if not existing.degree_name and deg_clean:
                        existing.degree_name = deg_clean
                    if not existing.start_year and start_year:
                        existing.start_year = start_year
                    if not existing.end_year and end_year:
                        existing.end_year = end_year
                    if not existing.field_of_study and fos_clean:
                        existing.field_of_study = fos_clean
                    if not existing.school_logo_url and school_logo:
                        existing.school_logo_url = school_logo
                    return

            educations.append(Education(
                school_name=s_clean,
                school_url=f"https://www.linkedin.com/school/{school_urn.split(':')[-1]}" if school_urn and ":" in school_urn else None,
                school_logo_url=school_logo,
                degree_name=deg_clean,
                field_of_study=fos_clean,
                start_year=start_year,
                end_year=end_year,
                grade=e.get("grade"),
                activities=act_clean,
                description=desc_clean,
            ))

        for container_key in ("educationView", "educations", "profileEducations", "education"):
            container = profile.get(container_key)
            if isinstance(container, dict):
                for el in container.get("elements", []):
                    add_edu(el)
            elif isinstance(container, list):
                for el in container:
                    add_edu(el)

        # Scan included list
        for item in included:
            if not isinstance(item, dict):
                continue
            type_str = item.get("$type", "")
            if "Education" in type_str or "schoolName" in item or "school" in item:
                add_edu(item)

        # Scan entity_map values for any resolved education entities
        for item in entity_map.values():
            if not isinstance(item, dict):
                continue
            type_str = item.get("$type", "")
            if "Education" in type_str or "schoolName" in item:
                add_edu(item)

        # Sort reverse-chronologically: Newest education first
        def _edu_sort_key(e: Education):
            end_y = e.end_year or 0
            start_y = e.start_year or 0
            return (end_y, start_y)

        educations.sort(key=_edu_sort_key, reverse=True)
        return educations

    @staticmethod
    def _extract_skills(profile: Dict[str, Any], entity_map: Dict[str, Any], included: List[Dict[str, Any]]) -> List[Skill]:
        skills: List[Skill] = []
        seen_names = set()

        def add_skill(name: Optional[str], endorsements: Optional[int] = None):
            if not name:
                return
            clean_name = str(name).strip()
            if not clean_name or is_masked(clean_name):
                return
            lower_name = clean_name.lower()
            if lower_name in seen_names:
                for s in skills:
                    if s.name.lower() == lower_name and endorsements and (not s.endorsement_count or endorsements > s.endorsement_count):
                        s.endorsement_count = endorsements
                return
            seen_names.add(lower_name)
            skills.append(Skill(name=clean_name, endorsement_count=endorsements))

        # 1. Scan included array for any Skill entities
        for item in included:
            if not isinstance(item, dict):
                continue
            type_str = item.get("$type", "")
            if "Skill" in type_str:
                name = (
                    item.get("name")
                    or (item.get("skill", {}).get("name") if isinstance(item.get("skill"), dict) else None)
                    or (item.get("standardizedSkill", {}).get("name") if isinstance(item.get("standardizedSkill"), dict) else None)
                    or item.get("title")
                    or (item.get("entityCustomSkill", {}).get("name") if isinstance(item.get("entityCustomSkill"), dict) else None)
                )
                count = (
                    item.get("endorsementCount")
                    or (item.get("endorsements", {}).get("paging", {}).get("total") if isinstance(item.get("endorsements"), dict) else None)
                    or (item.get("endorsedSkill", {}).get("endorsementCount") if isinstance(item.get("endorsedSkill"), dict) else None)
                )
                add_skill(name, count)

        # 2. Check profile entity direct collections
        for container_key in ("skillView", "skills", "profileSkills", "standardizedSkills"):
            container = profile.get(container_key)
            if isinstance(container, dict):
                elements = container.get("elements", [])
                if isinstance(elements, list):
                    for el in elements:
                        if isinstance(el, dict):
                            name = (
                                el.get("name")
                                or (el.get("skill", {}).get("name") if isinstance(el.get("skill"), dict) else None)
                                or el.get("title")
                            )
                            count = el.get("endorsementCount")
                            add_skill(name, count)

        return skills

    @staticmethod
    def _extract_certifications(profile: Dict[str, Any], entity_map: Dict[str, Any], included: List[Dict[str, Any]]) -> List[Certification]:
        certs: List[Certification] = []
        seen_keys = set()

        for item in included:
            if not isinstance(item, dict):
                continue
            type_str = item.get("$type", "")
            if "Certification" in type_str or "License" in type_str:
                name = item.get("name") or item.get("title")
                if name and not is_masked(name):
                    auth = item.get("authority") or item.get("issuingAuthority") or (item.get("company", {}).get("name") if isinstance(item.get("company"), dict) else None)
                    key = f"{str(name).lower()}_{str(auth).lower()}"
                    if key in seen_keys:
                        continue
                    seen_keys.add(key)
                    time_period = item.get("timePeriod", {}) or item.get("dateRange", {})
                    certs.append(Certification(
                        name=str(name).strip(),
                        authority=str(auth).strip() if auth else None,
                        license_number=item.get("licenseNumber"),
                        url=item.get("url"),
                        issue_date=VoyagerGraphParser._parse_date(time_period.get("startDate") if isinstance(time_period, dict) else None),
                        expiration_date=VoyagerGraphParser._parse_date(time_period.get("endDate") if isinstance(time_period, dict) else None),
                    ))
        return certs

    _PROFICIENCY_MAP = {
        "NATIVE_OR_BILINGUAL": "Native or bilingual proficiency",
        "FULL_PROFESSIONAL": "Full professional proficiency",
        "PROFESSIONAL_WORKING": "Professional working proficiency",
        "LIMITED_WORKING": "Limited working proficiency",
        "ELEMENTARY": "Elementary proficiency",
    }

    @staticmethod
    def _humanize_proficiency(raw: Optional[str]) -> Optional[str]:
        """Converts LinkedIn Voyager proficiency enum values to human-readable text."""
        if not raw:
            return None
        mapped = VoyagerGraphParser._PROFICIENCY_MAP.get(raw.upper())
        if mapped:
            return mapped
        return raw.replace("_", " ").capitalize()

    @staticmethod
    def _extract_languages(profile: Dict[str, Any], entity_map: Dict[str, Any], included: List[Dict[str, Any]]) -> List[Language]:
        languages: List[Language] = []
        seen_langs = set()

        for lang_item in included:
            if not isinstance(lang_item, dict):
                continue
            type_str = lang_item.get("$type", "")
            if "Language" in type_str:
                name = lang_item.get("name")
                if name and not is_masked(name):
                    clean_name = str(name).strip()
                    if clean_name.lower() in seen_langs:
                        continue
                    seen_langs.add(clean_name.lower())
                    languages.append(Language(
                        name=clean_name,
                        proficiency=VoyagerGraphParser._humanize_proficiency(lang_item.get("proficiency")),
                    ))
        return languages

    @staticmethod
    def _extract_contact_info(profile: Dict[str, Any], entity_map: Dict[str, Any], included: List[Dict[str, Any]]) -> ContactInfo:
        websites: List[str] = []
        twitter = None
        emails: List[str] = []
        phones: List[str] = []

        for item in included:
            if not isinstance(item, dict):
                continue
            type_str = item.get("$type", "")
            if "ProfileContactInfo" in type_str:
                for w in item.get("websites", []):
                    if isinstance(w, dict) and w.get("url"):
                        websites.append(w["url"])
                if item.get("twitter"):
                    twitter = item["twitter"]
                if item.get("emailAddress"):
                    emails.append(item["emailAddress"])

        return ContactInfo(
            websites=websites,
            twitter=twitter,
            emails=emails,
            phone_numbers=phones,
        )

    @staticmethod
    def _parse_date(date_val: Any) -> Optional[DateModel]:
        if not date_val:
            return None
        if isinstance(date_val, DateModel):
            return date_val
        if isinstance(date_val, int):
            if 1900 <= date_val <= 2100:
                return DateModel(year=date_val)
            return None
        if isinstance(date_val, str):
            date_str = date_val.strip()
            m = re.match(r"^(\d{4})(?:[-/](\d{1,2}))?", date_str)
            if m:
                year = int(m.group(1))
                month = int(m.group(2)) if m.group(2) else None
                return DateModel(year=year, month=month)
            return None
        if isinstance(date_val, dict):
            year = date_val.get("year") or date_val.get("startYear") or date_val.get("endYear")
            month = date_val.get("month") or date_val.get("startMonth") or date_val.get("endMonth")
            day = date_val.get("day")
            if year is not None or month is not None:
                try:
                    y_int = int(year) if year is not None and str(year).isdigit() else None
                    m_int = int(month) if month is not None and str(month).isdigit() else None
                    d_int = int(day) if day is not None and str(day).isdigit() else None
                    if y_int or m_int:
                        return DateModel(year=y_int, month=m_int, day=d_int)
                except Exception:
                    pass
        return None
