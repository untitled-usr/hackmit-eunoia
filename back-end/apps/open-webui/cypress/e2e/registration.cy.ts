// eslint-disable-next-line @typescript-eslint/triple-slash-reference
/// <reference path="../support/index.d.ts" />

// ADMIN_UID is the fixed system admin id from cypress/support/e2e.ts (server creates it at startup).

describe('Registration and Login', () => {
	after(() => {
		// eslint-disable-next-line cypress/no-unnecessary-waiting
		cy.wait(2000);
	});

	beforeEach(() => {
		cy.visit('/');
	});

	it('should register a new user via quick register', () => {
		cy.visit('/auth');
		cy.contains('button', '一键注册').click();
		cy.contains('您的用户 ID', { timeout: 20000 });
		cy.get('code').should(($el) => {
			expect($el.text().trim().length).to.be.greaterThan(8);
		});
	});

	it('can enter with the seeded admin uid', () => {
		const uid = Cypress.env('ADMIN_UID') as string;
		expect(uid).to.be.a('string').and.not.be.empty;
		cy.visit('/auth');
		cy.get('input[autocomplete="username"]').type(uid);
		cy.contains('button', '进入').first().click();
		cy.get('#chat-search', { timeout: 30000 }).should('exist');
		cy.get('body').then(($b) => {
			if ($b.find('button:contains("Okay, Let\'s Go!")').length) {
				cy.contains('button', "Okay, Let's Go!").click();
			}
		});
	});
});
