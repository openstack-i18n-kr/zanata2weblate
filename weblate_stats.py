#!/usr/bin/env python3

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or
# implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import argparse
import collections
import csv
import datetime
import io
import os
import json
import logging
import random
import re
import sys

import requests
import yaml

import wlc.config as cfg
from wlc import Weblate
from WeblateUtils import IniConfig
from weblate_records import (
    WeblateProject,
    WeblateObjectStats,
    WeblateProjectStats,
    WeblateUserStats,
    WeblateUserInfo,
    WeblateGroupInfo,
    WeblateTranslationInfo,
    WeblateComponentInfo,
    WeblateChangeInfo,
)

WEBLATE_HOST = "https://openstack.weblate.cloud"
WEBLATE_URI = WEBLATE_HOST + "/%s"
LOG = logging.getLogger("weblate_stats")

WEBLATE_VERSION_EXPR = r"^(master[-,a-z]*|stable-[a-z]+|openstack-user-survey)$"
WEBLATE_VERSION_PATTERN = re.compile(WEBLATE_VERSION_EXPR)


class WeblateUtility(object):
    """
    Utilities to invoke Weblate REST API.

    Reference
        https://docs.weblate.org/en/weblate-4.18.2/api.html#projects

        https://docs.weblate.org/en/weblate-4.18.2/api.html#get--api-users-(str-username)-statistics-
    """

    user_agents = [
        "Mozilla/5.0 (X11; Ubuntu; Linux x86_64) Gecko/20100101 Firefox/32.0",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_9_6) AppleWebKit/537.78.2",
        "Mozilla/5.0 (Windows NT 6.3; WOW64) Gecko/20100101 Firefox/32.0",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X) Chrome/37.0.2062.120",
        "Mozilla/5.0 (Windows NT 6.1; WOW64; Trident/7.0; rv:11.0) like Gecko",
    ]

    def __init__(
        self,
        wconfig,
        verify: bool = True,
        accept: str = "application/json, text/javascript",
        content_type: str = "application/json",
    ):
        self.url, self.key = wconfig.url, wconfig.key
        self.weblate_obj = Weblate()
        self.headers = {
            "Accept": accept,
            "Content-Type": content_type,
            "Authorization": "Token " + self.key,
        }
        self.verify = verify

    def read_uri(self, uri, headers):
        try:
            headers["User-Agent"] = random.choice(WeblateUtility.user_agents)
            req = requests.get(uri, headers=headers)
            return req.text
        except Exception as e:
            LOG.error(
                'Error "%(error)s" while reading uri %(uri)s', {"error": e, "uri": uri}
            )
            raise

    def read_json_from_uri(self, uri):
        data = self.read_uri(uri, self.headers)
        try:
            return json.loads(data)
        except Exception as e:
            LOG.error(
                'Error "%(error)s" parsing json from uri %(uri)s',
                {"error": e, "uri": uri},
            )
            raise

    def get_projects(self) -> list:
        uri = WEBLATE_URI % ("api/projects/")
        LOG.debug("Reading projects from %s" % uri)
        projects_data = self.read_json_from_uri(uri)
        return projects_data["results"]
        # return [project["slug"] for project in projects_data]

    def get_project_statistics(
        self, project_slug: str
    ) -> WeblateProjectStats:  # 3 유저-프로젝트 + 로케일
        uri = WEBLATE_URI % ("api/projects/%s/statistics/" % (project_slug))
        LOG.debug("Reading project statistics from %s" % uri)
        project_data = self.read_json_from_uri(uri)
        return WeblateProjectStats.from_dict(project_data)

    def get_object_statistics(self, obj: str) -> WeblateObjectStats:
        uri = WEBLATE_URI % ("api/%s/statistics/" % (obj))
        LOG.debug("Reading object statistics from %s" % uri)
        object_data = self.read_json_from_uri(uri)
        return WeblateObjectStats.from_dict(object_data)

    def get_users(self) -> list:
        uri = WEBLATE_URI % ("api/users/")
        LOG.debug("Reading users from %s" % uri)
        users_data = self.read_json_from_uri(uri)
        return users_data["results"]

    def get_user(self, username: str) -> WeblateUserInfo:  # 1 -> 유저 별 그룹정보
        uri = WEBLATE_URI % ("api/users/%s/" % (username))
        LOG.debug("Reading user from %s" % uri)
        user_data = self.read_json_from_uri(uri)
        return WeblateUserInfo.from_dict(user_data)

    def get_user_statistics(self, username: str) -> WeblateUserStats:  # 2 -> 토탈정보
        uri = WEBLATE_URI % ("api/users/%s/statistics/" % (username))
        LOG.debug("Reading user statistics from %s" % uri)
        user_data = self.read_json_from_uri(uri)
        return WeblateUserStats.from_dict(user_data)

    def get_group(self, group_id: int) -> WeblateGroupInfo:  # 2 -> 프로젝트
        uri = WEBLATE_URI % ("api/groups/%s/" % (group_id))
        LOG.debug("Reading group from %s" % uri)
        group_data = self.read_json_from_uri(uri)
        return WeblateUserInfo.from_dict(group_data)

    def get_projects(self) -> list:
        uri = WEBLATE_URI % ("api/projects/")
        LOG.debug("Reading projects from %s" % uri)
        projects_data = self.read_json_from_uri(uri)
        return projects_data["results"]
        # return [project["slug"] for project in projects_data]

    def get_component(
        self, project: str, component: str
    ) -> WeblateComponentInfo:  # 2 -> 프로젝트
        uri = WEBLATE_URI % ("api/components/%s/%s/" % (project, component))
        LOG.debug("Reading component from %s" % uri)
        component_data = self.read_json_from_uri(uri)
        return WeblateComponentInfo.from_dict(component_data)

    def get_translations(
        self, project: str, component: str, language: str
    ) -> WeblateTranslationInfo:  # 2 -> 프로젝트
        uri = WEBLATE_URI % (
            "api/translations/%s/%s/%s/" % (project, component, language)
        )
        LOG.debug("Reading component from %s" % uri)
        translation_data = self.read_json_from_uri(uri)
        return WeblateTranslationInfo.from_dict(translation_data)

    def get_change(self, id: int) -> WeblateChangeInfo:  # 2 -> 프로젝트
        uri = WEBLATE_URI % ("api/changes/%d/" % (id))
        LOG.debug("Reading change from %s" % uri)
        change_data = self.read_json_from_uri(uri)
        return WeblateChangeInfo.from_dict(change_data)

    ################

    # def _get_project_statistics(
    #     self, url: str
    # ) -> WeblateProjectStats:  # 3 유저-프로젝트 + 로케일
    #     uri = WEBLATE_URI % ("api/projects/%s/statistics/" % (project_slug))
    #     LOG.debug("Reading project statistics from %s" % uri)
    #     project_data = self.read_json_from_uri(uri)
    #     return WeblateProjectStats.from_dict(project_data)

    # def _get_object_statistics(self, url: str) -> WeblateObjectStats:
    #     uri = WEBLATE_URI % ("api/%s/statistics/" % (obj))
    #     LOG.debug("Reading object statistics from %s" % uri)
    #     object_data = self.read_json_from_uri(uri)
    #     return WeblateObjectStats.from_dict(object_data)

    # def _get_users(self, url: str) -> list:
    #     uri = WEBLATE_URI % ("api/users/")
    #     LOG.debug("Reading users from %s" % uri)
    #     users_data = self.read_json_from_uri(uri)
    #     return users_data["results"]

    # def _get_user(self, url: str) -> WeblateUserInfo:  # 1 -> 유저 별 그룹정보
    #     uri = WEBLATE_URI % ("api/users/%s/" % (username))
    #     LOG.debug("Reading user from %s" % uri)
    #     user_data = self.read_json_from_uri(uri)
    #     return WeblateUserInfo.from_dict(user_data)

    # def _get_user_statistics(self, url: str) -> WeblateUserStats:  # 2 -> 토탈정보
    #     uri = WEBLATE_URI % ("api/users/%s/statistics/" % (username))
    #     LOG.debug("Reading user statistics from %s" % uri)
    #     user_data = self.read_json_from_uri(uri)
    #     return WeblateUserStats.from_dict(user_data)

    # def _get_group(self, url: str) -> WeblateGroupInfo:  # 2 -> 프로젝트
    #     LOG.debug("Reading group from %s" % url)
    #     group_data = self.read_json_from_uri(url)
    #     return WeblateUserInfo.from_dict(group_data)

    # def _get_component(self, url: str) -> WeblateComponentInfo:
    #     LOG.debug("Reading group from %s" % url)
    #     group_data = self.read_json_from_uri(url)
    #     return None

    # def _get_component(self, url: str):
    #     LOG.debug("Reading group from %s" % url)
    #     group_data = self.read_json_from_uri(url)
    #     return None


class LanguageTeam(object):
    def __init__(self, language_code, team_info):
        self.language_code = language_code
        self.language = team_info["language"]
        # Weblate ID which only consists of numbers is a valid ID in Weblate
        # Such entry is interpreted as integer unless it is quoted
        # in the YAML file. Exnsure to stringify them.
        self.translators = [str(i) for i in team_info["translators"]]
        self.reviewers = [str(i) for i in team_info.get("reviewers", [])]
        self.coordinators = [str(i) for i in team_info.get("coordinators", [])]

    @classmethod
    def load_from_language_team_yaml(cls, translation_team_uri, lang_list):
        LOG.debug("Process list of language team from uri: %s", translation_team_uri)

        content = yaml.safe_load(io.open(translation_team_uri, "r"))

        if lang_list:
            lang_notfound = [
                lang_code for lang_code in lang_list if lang_code not in content
            ]
            if lang_notfound:
                LOG.error(
                    "Language %s not tound in %s.",
                    ", ".join(lang_notfound),
                    translation_team_uri,
                )
                sys.exit(1)

        return [
            cls(lang_code, team_info)
            for lang_code, team_info in content.items()
            if not lang_list or lang_code in lang_list
        ]


class User(object):
    trans_fields = ["total", "Translated", "NeedReview", "Approved", "Rejected"]
    review_fields = ["total", "Approved", "Rejected"]

    def __init__(self, user_id, language_code):
        self.user_id = user_id
        self.lang = language_code
        self.stats = collections.defaultdict(dict)

    def __str__(self):
        return "<%s: user_id=%s, lang=%s, stats=%s" % (
            self.__class__.__name__,
            self.user_id,
            self.lang,
            self.stats,
        )

    # def __repr__(self):
    #     return repr(self.convert_to_serializable_data())

    def __lt__(self, other):
        if self.lang != other.lang:
            return self.lang < other.lang
        else:
            return self.user_id < other.user_id

    def read_from_weblate_stats(self, weblate_stats, project_list, version_list):
        # data format (Zanata 4.3.3)
        # [
        #     {
        #         "savedDate": "2020-09-06",
        #         "projectSlug": "i18n",
        #         "projectName": "i18n",
        #         "versionSlug": "master",
        #         "localeId": "ko-KR",
        #         "localeDisplayName": "Korean (South Korea)",
        #         "savedState": "Translated",
        #         "wordCount": 119
        #     }
        # ]
        for weblate_stat in weblate_stats:
            project_id = weblate_stat["projectSlug"]
            version = weblate_stat["versionSlug"]
            lang = weblate_stat["localeId"]
            stat_state = weblate_stat["savedState"]
            word_count = weblate_stat["wordCount"]

            if project_list and project_id not in project_list:  # pid가 없으면
                continue

            if version_list and version not in version_list:  # vid가 없으면
                continue

            if self.lang != lang:  # lang이 다르면
                continue

            my_project = self.stats[project_id]

            if version not in my_project:
                my_project[version] = {
                    "translation-stats": collections.defaultdict(int),
                    "review-stats": collections.defaultdict(int),
                }
            my_version = my_project[version]

            if stat_state in self.trans_fields:
                my_trans_stats = my_version["translation-stats"]
                my_trans_stats[stat_state] += word_count
                my_trans_stats["total"] += word_count

            if stat_state in self.review_fields:
                my_review_stats = my_version["review-stats"]
                my_review_stats[stat_state] += word_count
                my_review_stats["total"] += word_count

    def populate_total_stats(self):
        total_trans = dict([(k, 0) for k in self.trans_fields])
        total_review = dict([(k, 0) for k in self.review_fields])

        for project_id, versions in self.stats.items():
            for version, stats in versions.items():
                trans_stats = stats.get("translation-stats", {})
                for k in self.trans_fields:
                    total_trans[k] += trans_stats.get(k, 0)
                review_stats = stats.get("review-stats", {})
                for k in self.review_fields:
                    total_review[k] += review_stats.get(k, 0)
        self.stats["__total__"]["translation-stats"] = total_trans
        self.stats["__total__"]["review-stats"] = total_review

    def needs_output(self, include_no_activities):
        if include_no_activities:
            return True
        return bool(self.stats) and all(self.stats.values())

    @staticmethod
    def get_flattened_data_title():
        return [
            "user_id",
            "lang",
            "project",
            "version",
            "translation-total",
            "translated",
            "needReview",
            "approved",
            "rejected",
            "review-total",
            "review-approved",
            "review-rejected",
        ]

    def convert_to_flattened_data(self, detail=False):
        self.populate_total_stats()

        data = []

        for project_id, versions in self.stats.items():
            if project_id == "__total__":
                continue
            for version, stats in versions.items():
                trans_stats = stats.get("translation-stats", {})
                review_stats = stats.get("review-stats", {})
                if detail:
                    data.append(
                        [self.user_id, self.lang, project_id, version]
                        + [trans_stats.get(k, 0) for k in self.trans_fields]
                        + [review_stats.get(k, 0) for k in self.review_fields]
                    )

        data.append(
            [self.user_id, self.lang, "-", "-"]
            + [
                self.stats["__total__"]["translation-stats"][k]
                for k in self.trans_fields
            ]
            + [self.stats["__total__"]["review-stats"][k] for k in self.review_fields]
        )

        return data

    def convert_to_serializable_data(self, detail):
        self.populate_total_stats()
        return {
            "user_id": self.user_id,
            "lang": self.lang,
            "stats": (self.stats if detail else self.stats["__total__"]),
        }


def write_stats_to_file(users, output_file, file_format, include_no_activities, detail):
    users = sorted([user for user in users if user.needs_output(include_no_activities)])

    if file_format == "csv":
        _write_stats_to_csvfile(users, output_file, detail)
    else:
        _write_stats_to_jsonfile(users, output_file, detail)
    LOG.info("Stats has been written to %s", output_file)


def _write_stats_to_csvfile(users, output_file, detail):
    with open(output_file, "w") as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow(User.get_flattened_data_title())
        for user in users:
            writer.writerows(user.convert_to_flattened_data(detail))


def _write_stats_to_jsonfile(users, output_file, detail):
    users = [user.convert_to_serializable_data(detail) for user in users]
    with open(output_file, "w") as f:
        f.write(json.dumps(users, indent=4, sort_keys=True))


def _comma_separated_list(s):
    return s.split(",")


def main():
    # Loads weblate.ini configuration file
    try:
        wc = IniConfig(os.path.expanduser("~/.config/weblate.ini"))
    except ValueError as e:
        sys.exit(e)

    default_end_date = datetime.datetime.now()
    default_start_date = default_end_date - datetime.timedelta(days=180)
    default_start_date = default_start_date.strftime("%Y-%m-%d")
    default_end_date = default_end_date.strftime("%Y-%m-%d")

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "-s",
        "--start-date",
        default=default_start_date,
        help=("Specify the start date. " "Default:%s" % default_start_date),
    )
    parser.add_argument(
        "-e",
        "--end-date",
        default=default_end_date,
        help=("Specify the end date. " "Default:%s" % default_end_date),
    )
    parser.add_argument(
        "-o",
        "--output-file",
        help=("Specify the output file. " "Default: weblate_stats_output.{csv,json}."),
    )
    parser.add_argument(
        "-p",
        "--project",
        type=_comma_separated_list,
        help=(
            "Specify project(s). Comma-separated list. "
            "Otherwise all Weblate projects are processed."
        ),
    )
    parser.add_argument(
        "-l",
        "--lang",
        type=_comma_separated_list,
        help=(
            "Specify language(s). Comma-separated list. "
            "Language code like zh-CN, ja needs to be used. "
            "Otherwise all languages are processed."
        ),
    )
    parser.add_argument(
        "-t",
        "--target-version",
        type=_comma_separated_list,
        help=(
            "Specify version(s). Comma-separated list. "
            "Otherwise all available versions are "
            "processed."
        ),
    )
    parser.add_argument(
        "-u",
        "--user",
        type=_comma_separated_list,
        help=(
            "Specify user(s). Comma-separated list. "
            "Otherwise all users are processed."
        ),
    )
    parser.add_argument(
        "--detail",
        action="store_true",
        help=(
            "If specified, statistics per project "
            "and version are output in addition to "
            "total statistics."
        ),
    )
    parser.add_argument(
        "--include-no-activities",
        action="store_true",
        help=(
            "If specified, stats for users with no "
            "activities are output as well."
            "By default, stats only for users with "
            "any activities are output."
        ),
    )
    parser.add_argument(
        "-f",
        "--format",
        default="csv",
        choices=["csv", "json"],
        help="Output file format.",
    )
    parser.add_argument(
        "--no-verify",
        action="store_false",
        dest="verify",
        help="Do not perform HTTPS certificate verification",
    )
    parser.add_argument("--debug", action="store_true", help="Enable debug message.")
    parser.add_argument("user_yaml", help="YAML file of the user list")
    options = parser.parse_args()

    logging_level = logging.DEBUG if options.debug else logging.INFO
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    handler = logging.StreamHandler()
    handler.setLevel(logging_level)
    handler.setFormatter(formatter)
    LOG.setLevel(logging_level)
    LOG.addHandler(handler)

    language_teams = LanguageTeam.load_from_language_team_yaml(
        options.user_yaml, options.lang
    )

    versions = [v.replace("/", "-") for v in options.target_version or []]
    users = get_weblate_stats(
        wc,
        options.verify,
        options.start_date,
        options.end_date,
        language_teams,
        options.project,
        versions,
        options.user,
    )

    output_file = options.output_file or "weblate_stats_output.%s" % options.format

    write_stats_to_file(
        users,
        output_file,
        options.format,
        options.include_no_activities,
        options.detail,
    )


def get_weblate_stats(
    wc,
    verify,
    start_date,
    end_date,
    language_teams,
    project_list,
    version_list,
    user_list,
):
    LOG.info(
        "Getting Weblate contributors statistics (from %s to %s) ...",
        start_date,
        end_date,
    )

    weblateUtil = WeblateUtility(wc, verify)
    users = []
    for team in language_teams:
        users += [User(user_id, team.language_code) for user_id in team.translators]

    if not project_list:
        project_list = weblateUtil.get_projects()

    project_stats_list = []
    for project in project_list:
        project_stat = weblateUtil.get_project_statistics(project["slug"])
        project_stats_list.append(project_stat)

    for user in users:
        if user_list and user.user_id not in user_list:
            continue
        LOG.info(
            "Getting for user %(user_id)s %(user_lang)s",
            {"user_id": user.user_id, "user_lang": user.lang},
        )
        data = weblateUtil.get_user_statistics(user.user_id)
        LOG.debug("Got: %s", data)

        user.read_from_weblate_stats(data, project_list, version_list)
        LOG.debug("=> %s", user)

    return users


if __name__ == "__main__":
    main()
