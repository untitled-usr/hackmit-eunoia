/// <reference types="cypress" />
// eslint-disable-next-line @typescript-eslint/triple-slash-reference
/// <reference path="../support/index.d.ts" />

const ACTING_STORAGE_KEY = 'actingUid';

const loginWithUid = (userId: string) => {
	return cy.session(
		userId,
		() => {
			localStorage.setItem('locale', 'en-US');
			cy.visit('/auth');
			cy.get('input[autocomplete="username"]').clear().type(userId);
			cy.contains('button', '进入').first().click();
			cy.get('#chat-search', { timeout: 30000 }).should('exist');
			cy.get('body').then(($b) => {
				if ($b.find('button:contains("Okay, Let\'s Go!")').length) {
					cy.contains('button', "Okay, Let's Go!").click();
				}
			});
		},
		{
			validate: () => {
				cy.window().then((win) => {
					expect(win.localStorage.getItem(ACTING_STORAGE_KEY), 'acting uid in storage').to.be.a(
						'string'
					).and.not.be.empty;
				});
			}
		}
	);
};

/** Fixed system admin id (matches backend SYSTEM_ADMIN_USER_ID); created at server startup. */
const SYSTEM_ADMIN_USER_ID = '00000000-0000-4000-8000-000000000001';

const seedAdminUid = () => {
	Cypress.env('ADMIN_UID', SYSTEM_ADMIN_USER_ID);
};

const loginAdmin = () => {
	const uid = Cypress.env('ADMIN_UID') as string;
	expect(uid, 'System admin uid (fixed UUID from server bootstrap)').to.be.a('string').and.not.be
		.empty;
	return loginWithUid(uid);
};

Cypress.Commands.add('loginAdmin', () => loginAdmin());

before(() => {
	seedAdminUid();
});
